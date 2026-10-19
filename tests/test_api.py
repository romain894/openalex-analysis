"""Library regression tests using real PyAlex and urllib3 with mocked HTTP."""

from io import BytesIO
import json
import logging
from pathlib import Path
import socket
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
from pyalex import Works
from pyalex import config as pyalex_config
from pyalex.api import QueryError
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import NewConnectionError, ReadTimeoutError
from urllib3.response import HTTPResponse

from openalex_analysis.data import (
    AuthorsData, InstitutionsData, WorksData, check_if_entity_exists,
    config, get_info_about_entity, get_name_of_entity, load_config_from_file,
)
from openalex_analysis.data.entities_data import set_default_config


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch, tmp_path):
    saved = config.copy()
    saved_pyalex = pyalex_config.copy()
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    set_default_config()
    config.project_data_folder_path = str(tmp_path / 'cache')
    config.disable_tqdm_loading_bar = True

    def no_network(*args, **kwargs):
        raise AssertionError('Unmocked network access')

    monkeypatch.setattr(socket.socket, 'connect', no_network)
    yield
    config.clear()
    for key, value in saved.items():
        setattr(config, key, value)
    pyalex_config.clear()
    pyalex_config.update(saved_pyalex)


@pytest.fixture
def http(monkeypatch):
    """Mock wire responses, preserving PyAlex sessions, errors and retry logic."""
    calls = []
    responses = []
    pending = {}
    original_send = requests.adapters.HTTPAdapter.send

    def send(adapter, request, **kwargs):
        pending.update(request=request, options=kwargs)
        return original_send(adapter, request, **kwargs)

    def make_request(pool, connection, method, url, **kwargs):
        request = pending['request']
        calls.append((request, pending['options']))
        assert responses, 'Unexpected extra HTTP attempt'
        result = responses.pop(0)
        if isinstance(result, requests.Timeout):
            raise ReadTimeoutError(pool, url, str(result))
        if isinstance(result, requests.ConnectionError):
            raise NewConnectionError(connection, str(result))
        status, body, headers = result
        return HTTPResponse(body=BytesIO(json.dumps(body).encode()), status=status,
                            headers=headers, preload_content=False, request_method=method)

    monkeypatch.setattr(requests.adapters.HTTPAdapter, 'send', send)
    monkeypatch.setattr(HTTPConnectionPool, '_make_request', make_request)
    return calls, responses


def listed(records, count=None, cursor=None):
    return 200, {'results': records, 'meta': {
        'count': len(records) if count is None else count, 'next_cursor': cursor}}, {}


def entity(ident='W1', **extra):
    return {'id': 'https://openalex.org/' + ident, 'display_name': ident, **extra}


@pytest.mark.parametrize('total', [0, 1, 100, 101, 200, 201])
def test_download_pages_and_cursor(http, total):
    calls, responses = http
    responses.append(listed([], count=total))
    for start in range(0, total, 100):
        next_cursor = f'cursor-{start + 100}' if start + 100 < total else None
        responses.append(listed([entity(f'W{i}') for i in range(start, min(start + 100, total))],
                                count=total, cursor=next_cursor))
    data = WorksData('I1')
    assert len(data.entities_df) == total
    assert data.per_page == 100
    assert config.n_max_entities == 10000
    expected_requests = 1 + (total + 99) // 100
    assert len(calls) == expected_requests
    assert parse_qs(urlsplit(calls[0][0].url).query)['per-page'] == ['1']
    for page, (request, _) in enumerate(calls[1:]):
        query = parse_qs(urlsplit(request.url).query)
        assert query['per-page'] == ['100']
        assert query['cursor'] == ['*' if page == 0 else f'cursor-{page * 100}']
        assert 'page' not in query
        assert query['filter'] == ['institutions.id:I1']
    assert data.entity_downloading_progress_percentage == 100
    WorksData('I1')
    assert len(calls) == expected_requests  # fresh Parquet cache avoids HTTP
    assert not responses


@pytest.mark.parametrize('limit', [0, 1, 100, 101])
def test_explicit_cap_is_hard_bound(http, limit):
    calls, responses = http
    config.n_max_entities = limit
    responses.append(listed([], count=300))
    for start in range(0, limit, 100):
        responses.append(listed([entity(f'W{i}') for i in range(start, start + 100)],
                                count=300, cursor='next'))
    assert len(WorksData('I1').entities_df) == limit
    assert len(calls) == 1 + (limit + 99) // 100


@pytest.mark.parametrize('limit, expected_rows', [(None, 3), (10000, 3), (3, 3), (2, 2)])
def test_page_exceeding_preflight_count_is_kept_within_configured_cap(http, limit, expected_rows):
    calls, responses = http
    config.n_max_entities = limit
    responses.extend([listed([], count=1), listed([entity('W1'), entity('W2'), entity('W3')], count=3)])
    with pytest.warns(UserWarning, match='entities_list was too short, appending the entity'):
        data = WorksData('I1')
    assert data.entities_df.id.tolist() == ['https://openalex.org/W' + str(i) for i in range(1, expected_rows + 1)]
    assert data.entity_downloading_progress_percentage == 100
    assert len(WorksData('I1').entities_df) == expected_rows
    assert len(calls) == 2


@pytest.mark.parametrize('cls, endpoint, nested', [
    (WorksData, 'works', {'authorships': {'institutions': {'id': 'I1'}}}),
    (AuthorsData, 'authors', {'affiliations': {'institution': {'id': 'I1'}}}),
    (InstitutionsData, 'institutions', {'country_code': 'FR'}),
])
def test_public_constructors_nested_filters_and_auth(http, cls, endpoint, nested, caplog):
    calls, responses = http
    config.api_key = 'private-test-credential'
    config.email = 'contact@example.org'
    prefix = {'works': 'W', 'authors': 'A', 'institutions': 'I'}[endpoint]
    responses.extend([listed([], count=1), listed([entity(prefix + '1')])])
    with caplog.at_level(logging.DEBUG):
        data = cls(extra_filters=nested)
    assert len(data.entities_df) == 1
    for request, _ in calls:
        assert urlsplit(request.url).path == '/' + endpoint
        assert request.headers['Authorization'] == 'Bearer private-test-credential'
        assert request.headers['From'] == 'contact@example.org'
        assert 'api_key' not in request.url
    assert 'private-test-credential' not in caplog.text
    assert 'private-test-credential' not in data.get_database_file_name()


def test_environment_key_and_toml_configuration(http, monkeypatch, tmp_path):
    calls, responses = http
    monkeypatch.setenv('OPENALEX_API_KEY', 'environment-key')
    set_default_config()
    path = tmp_path / 'config.toml'
    path.write_text('max_retries = 1\nretry_backoff_factor = 0.5\nretry_http_codes = [429, 503]\n')
    load_config_from_file(str(path))
    assert config.api_key == pyalex_config.api_key == 'environment-key'
    assert config.n_max_entities == 10000
    assert config.max_retries == pyalex_config.max_retries == 1
    assert config.retry_backoff_factor == pyalex_config.retry_backoff_factor == 0.5
    assert config.retry_http_codes == pyalex_config.retry_http_codes == [429, 503]
    responses.append(listed([]))
    WorksData().get_count_entities_matched({})
    assert calls[0][0].headers['Authorization'] == 'Bearer environment-key'


def test_anonymous_access_and_pyalex_authentication(http):
    calls, responses = http
    responses.extend([listed([]), listed([])])
    WorksData().get_count_entities_matched({})
    assert 'Authorization' not in calls[0][0].headers
    config.api_key = 'configured-key'
    WorksData().get_count_entities_matched({})
    assert calls[1][0].headers['Authorization'] == 'Bearer configured-key'


@pytest.mark.parametrize('status', [429, 500, 502, 503, 504])
def test_pyalex_transient_status_retries(http, monkeypatch, status):
    calls, responses = http
    waits = []
    monkeypatch.setattr('urllib3.util.retry.time.sleep', waits.append)
    responses.extend([(status, {}, {'Retry-After': '5'}), listed([entity()])])
    result = WorksData().get_multiple_entities_from_id(['W1'], return_dataframe=False)
    assert result[0]['id'].endswith('/W1')
    assert len(calls) == 2
    assert waits == [5]


@pytest.mark.parametrize('failure', [requests.Timeout, requests.ConnectionError])
def test_pyalex_transport_errors_and_backoff(http, monkeypatch, failure):
    calls, responses = http
    waits = []
    monkeypatch.setattr('urllib3.util.retry.time.sleep', waits.append)
    config.max_retries = 2
    responses.extend([failure('synthetic transport failure'), failure('synthetic transport failure'), listed([])])
    assert WorksData().get_count_entities_matched({}) == 0
    assert len(calls) == 3
    assert waits == [4]  # PyAlex/urllib3: no initial delay, then factor * 2.


@pytest.mark.parametrize('retries', [0, 1, 3])
@pytest.mark.parametrize('failure', [429, 503, requests.Timeout])
def test_pyalex_maximum_retries(http, monkeypatch, retries, failure):
    calls, responses = http
    monkeypatch.setattr('urllib3.util.retry.time.sleep', lambda seconds: None)
    config.max_retries = retries
    item = failure('synthetic timeout') if failure is requests.Timeout else (failure, {}, {})
    responses.extend([item] * (retries + 1))
    expected = requests.ConnectionError if failure is requests.Timeout else requests.exceptions.RetryError
    with pytest.raises(expected):
        WorksData().get_count_entities_matched({})
    assert len(calls) == retries + 1


@pytest.mark.parametrize('status, body, expected, message', [
    (400, {'error': 'Invalid query parameters error.', 'message': 'invalid_filter is not a valid field'}, QueryError, 'invalid_filter'),
    (401, {'error': 'API key required'}, QueryError, 'configure a valid API key'),
    (403, {'error': 'Forbidden'}, requests.HTTPError, '403'),
    (404, {'error': 'Not found'}, requests.HTTPError, '404'),
])
def test_pyalex_error_types_and_messages_preserved(http, status, body, expected, message):
    calls, responses = http
    responses.append((status, body, {}))
    with pytest.raises(expected, match=message):
        get_name_of_entity('I1')
    assert len(calls) == 1


def test_entity_helpers_and_existence(http):
    calls, responses = http
    responses.extend([(200, entity('I1'), {}), (200, entity('A1'), {}),
                      (200, entity('I1'), {}), (404, {}, {}), (503, {}, {})])
    assert get_name_of_entity('I1') == 'I1'
    assert get_info_about_entity('A1', return_as_pd_series=False) == {'display_name': 'A1'}
    assert check_if_entity_exists('I1') is True
    assert check_if_entity_exists('I2') is False
    config.max_retries = 0
    with pytest.raises(requests.exceptions.RetryError):
        check_if_entity_exists('I3')
    assert [urlsplit(request.url).path for request, _ in calls] == [
        '/institutions/I1', '/authors/A1', '/institutions/I1', '/institutions/I2', '/institutions/I3']


@pytest.mark.parametrize('count', [0, 1, 100, 101, 200])
def test_id_batch_boundaries_and_missing_duplicates(http, count):
    calls, responses = http
    ids = [f'I{i}' for i in range(count)]
    for start in range(0, count, 100):
        responses.append(listed([entity(ident) for ident in reversed(ids[start:start + 100])]))
    data = InstitutionsData()
    result = data.get_multiple_entities_from_id(ids, return_dataframe=False)
    assert [row['id'].split('/')[-1] for row in result] == ids
    assert len(calls) == (count + 99) // 100
    responses.append(listed([entity('I1')]))
    assert data.get_multiple_entities_from_id(['I1', 'I0', 'I1'], return_dataframe=False) == [entity('I1'), None, entity('I1')]


@pytest.mark.parametrize('count', [0, 1, 60, 61, 120])
def test_doi_batch_boundaries(http, count):
    calls, responses = http
    dois = [f'10.1234/{i}' for i in range(count)]
    for start in range(0, count, 60):
        responses.append(listed([entity(f'W{i}', doi='https://doi.org/' + dois[i])
                                 for i in range(start, min(start + 60, count))]))
    result = WorksData().get_multiple_works_from_doi(dois, return_dataframe=False)
    assert [row['doi'] for row in result] == ['https://doi.org/' + doi for doi in dois]
    assert len(calls) == (count + 59) // 60


def test_credentials_rejected_before_cache_keys_or_logs(http, caplog):
    calls, _ = http
    data = WorksData('I1', create_dataframe=False)
    data.extra_filters = {'authorships.apiKey': 'sensitive-key'}
    config.log_level = 'DEBUG'
    with caplog.at_level(logging.DEBUG):
        for method in [data.get_database_file_name, data.get_api_query,
                       data.load_entities_dataframe, data.download_list_entities]:
            with pytest.raises(ValueError, match='config.api_key'):
                method()
        with pytest.raises(ValueError, match='config.api_key'):
            WorksData().get_count_entities_matched({'api_key': 'sensitive-key'})
    assert not calls
    assert 'sensitive-key' not in caplog.text


def test_cursor_authentication_failure_does_not_write_partial_dataset(http):
    calls, responses = http
    responses.extend([listed([], count=101),
                      listed([entity(f'W{i}') for i in range(100)], count=101, cursor='next'),
                      (401, {'error': 'API key required'}, {})])
    with pytest.raises(QueryError, match='configure a valid API key'):
        WorksData('I1')
    assert len(calls) == 3
    assert not list(Path(config.project_data_folder_path).glob('*.parquet'))


def test_pyalex_owns_paginator_session(http):
    from pyalex.api import Paginator
    _, responses = http
    responses.extend([listed([entity()], count=2, cursor='next'), listed([entity('W2')], count=2)])
    pager = Works().paginate(per_page=100, n_max=2)
    assert isinstance(pager, Paginator)
    session = pager._session
    assert session.get_adapter('https://').max_retries.total == config.max_retries
    assert len(list(pager)) == 2
    assert pager._session is session


@pytest.mark.xfail(strict=True, reason='PyAlex 0.21 hardcodes the public host for regular queries; fix upstream.')
def test_configured_api_url_upstream_gap(http):
    calls, responses = http
    config.openalex_url = 'https://example.org/openalex'
    assert pyalex_config.openalex_url == config.openalex_url
    responses.append(listed([]))
    WorksData().get_count_entities_matched({})
    assert calls[0][0].url.startswith('https://example.org/openalex/')
