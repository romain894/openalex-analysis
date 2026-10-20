"""Library regression tests using real PyAlex and urllib3 with mocked HTTP."""

from io import BytesIO
import json
import logging
from pathlib import Path
import socket
import sqlite3
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
import requests
from pyalex import Works
from pyalex import config as pyalex_config
from pyalex.api import QueryError, not_, or_
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import NewConnectionError, ReadTimeoutError
from urllib3.response import HTTPResponse

from openalex_analysis.data import (
    AuthorsData, ConceptsData, InstitutionsData, PublishersData, SourcesData, TopicsData,
    WorksData, CacheMiss, QueryCache, check_if_entity_exists,
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
    config.query_cache_path = str(tmp_path / 'queries' / 'cache.sqlite3')
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
    assert not calls
    assert data.entities_df is None
    data.load_entities_dataframe()
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
    cached = WorksData('I1')
    cached.load_entities_dataframe()
    pd.testing.assert_frame_equal(data.entities_df, cached.entities_df)
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
    assert len(WorksData('I1', create_dataframe=True).entities_df) == limit
    assert len(calls) == 1 + (limit + 99) // 100


@pytest.mark.parametrize('limit, expected_rows', [(None, 3), (10000, 3), (3, 3), (2, 2)])
def test_page_exceeding_preflight_count_is_kept_within_configured_cap(http, limit, expected_rows):
    calls, responses = http
    config.n_max_entities = limit
    responses.extend([listed([], count=1), listed([entity('W1'), entity('W2'), entity('W3')], count=3)])
    with pytest.warns(UserWarning, match='entities_list was too short, appending the entity'):
        data = WorksData('I1', create_dataframe=True)
    assert data.entities_df.id.tolist() == ['https://openalex.org/W' + str(i) for i in range(1, expected_rows + 1)]
    assert data.entity_downloading_progress_percentage == 100
    assert len(WorksData('I1', create_dataframe=True).entities_df) == expected_rows
    assert len(calls) == 2


@pytest.mark.parametrize('cached_count', [0, 100])
@pytest.mark.parametrize('limit', [None, 10000, 150, 0])
def test_cached_count_does_not_truncate_entity_download(http, cached_count, limit):
    calls, responses = http
    config.n_max_entities = limit
    data = WorksData('I1')
    QueryCache().set('works', 'count', {'filter': data.get_api_query()}, cached_count)
    total = 250
    expected = total if limit is None else min(total, limit)
    responses.append(listed([], count=total))
    for start in range(0, expected, 100):
        end = min(start + 100, total)
        cursor = f'cursor-{end}' if end < total else None
        responses.append(listed([entity(f'W{i}') for i in range(start, end)], count=total, cursor=cursor))

    data.load_entities_dataframe()
    assert len(data.entities_df) == expected
    if expected:
        assert data.entities_df.id.tolist() == [f'https://openalex.org/W{i}' for i in range(expected)]
    assert len(calls) == 1 + (expected + 99) // 100
    assert parse_qs(urlsplit(calls[0][0].url).query)['per-page'] == ['1']
    assert not responses


@pytest.mark.parametrize('both_filters, either_filters', [
    ({'topics.id': ['T1', 'T2']}, or_({'topics.id': ['T1', 'T2']})),
    ({'topics': {'id': ['T1', 'T2']}}, {'topics': or_({'id': ['T1', 'T2']})}),
])
def test_parquet_cache_keeps_and_or_queries_separate(http, both_filters, either_filters):
    calls, responses = http
    both = WorksData(extra_filters=both_filters)
    either = WorksData(extra_filters=either_filters)
    assert both.database_file_path != either.database_file_path
    responses.extend([listed([], count=1), listed([entity('W1')]),
                      listed([], count=2), listed([entity('W1'), entity('W2')])])
    both.load_entities_dataframe()
    either.load_entities_dataframe()
    assert both.entities_df.id.tolist() == ['https://openalex.org/W1']
    assert either.entities_df.id.tolist() == ['https://openalex.org/W1', 'https://openalex.org/W2']
    both.load_entities_dataframe()
    either.load_entities_dataframe()
    assert len(calls) == 4
    assert not responses


def test_parquet_key_serialization_preserves_logical_filter_values(http):
    expression = not_('ice age')
    data = WorksData(extra_filters={'title.search': expression})
    assert data.get_database_file_name() == data.get_database_file_name()
    assert expression.value == 'ice age'


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
        data = cls(extra_filters=nested, create_dataframe=True)
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
        WorksData('I1', create_dataframe=True)
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


@pytest.mark.parametrize('filters', [
    {'institutions': {'id': 'I1'}},
    {'topics': or_({'id': ['T1', 'T2']})},
])
def test_query_cache_second_count_avoids_http(http, tmp_path, filters):
    from openalex_analysis.data import QueryCache
    calls, responses = http
    responses.append(listed([], count=42))
    cache = QueryCache(tmp_path / 'query-cache.sqlite3')
    parameters = {'filter': filters}
    def fetch():
        return Works().filter(**parameters['filter']).count()
    assert cache.get_or_fetch('works', 'count', parameters, fetch) == 42
    assert cache.get_or_fetch('works', 'count', parameters, fetch) == 42
    assert len(calls) == 1
    with sqlite3.connect(cache.path) as db:
        saved_params = json.loads(db.execute('SELECT parameters_json FROM query_cache').fetchone()[0])
    assert saved_params['filter'] == parse_qs(urlsplit(calls[0][0].url).query)['filter'][0]


@pytest.mark.parametrize('mode', ['auto', 'refresh'])
def test_query_cache_preserves_identity_when_pyalex_mutates_filters(http, tmp_path, mode):
    from openalex_analysis.data import QueryCache
    calls, responses = http
    responses.append(listed([], count=42))
    cache = QueryCache(tmp_path / 'query-cache.sqlite3')
    parameters = {'filter': {'title': {'search': not_('ice age')}}}
    key = cache.make_key('works', 'count', parameters)

    def fetch():
        return Works().filter(**parameters['filter']).count()

    assert cache.get_or_fetch('works', 'count', parameters, fetch, mode=mode) == 42
    original = {'filter': {'title': {'search': not_('ice age')}}}
    different = {'filter': {'title': {'search': not_('ice+age')}}}
    assert cache.get('works', 'count', different) is None
    assert cache.get_or_fetch('works', 'count', original,
                              lambda: pytest.fail('Original query was not cached')) == 42
    assert len(calls) == 1
    with sqlite3.connect(cache.path) as db:
        saved_key, params = db.execute('SELECT query_hash, parameters_json FROM query_cache').fetchone()
    assert saved_key == key
    assert json.loads(params)['filter'] == parse_qs(urlsplit(calls[0][0].url).query)['filter'][0]


def test_query_cache_complete_pyalex_groups_avoid_http(http, tmp_path):
    from openalex_analysis.data import QueryCache
    calls, responses = http
    pages = [
        {'meta': {'count': 42, 'next_cursor': 'next'}, 'group_by': [{'key': '2020', 'count': 20}]},
        {'meta': {'count': 42, 'next_cursor': None}, 'group_by': [{'key': '2021', 'count': 22}]},
    ]
    responses.extend((200, page, {}) for page in pages)
    cache = QueryCache(tmp_path / 'query-cache.sqlite3')
    parameters = {'filter': {'institutions': {'id': 'I1'}}, 'group_by': 'publication_year'}
    def fetch_pages():
        return Works().filter(**parameters['filter']).group_by('publication_year').paginate(per_page=100, n_max=None)
    assert cache.get_or_fetch_pages('works', parameters, fetch_pages) == pages
    assert cache.get_or_fetch_pages('works', parameters, fetch_pages) == pages
    assert len(calls) == 2


def grouped(groups, cursor=None, total=1_000_000):
    return 200, {'meta': {'count': total, 'groups_count': len(groups) or None,
                         'next_cursor': cursor}, 'group_by': groups}, {}


class TestAggregationQueries:
    @pytest.mark.parametrize('cls, endpoint', [
        (WorksData, 'works'), (AuthorsData, 'authors'), (InstitutionsData, 'institutions'),
        (SourcesData, 'sources'), (TopicsData, 'topics'), (ConceptsData, 'concepts'),
        (PublishersData, 'publishers'),
    ])
    @pytest.mark.parametrize('total', [0, 1_000_000_000])
    def test_count_is_full_corpus_and_cached_across_instances(self, http, cls, endpoint, total):
        calls, responses = http
        config.n_max_entities = 0
        responses.append(listed([], count=total))
        data = cls()
        assert data.get_count() == total
        assert cls().get_count() == total
        assert data.get_count(mode='offline') == total
        assert data.entities_df is None
        assert not Path(config.project_data_folder_path).exists()
        assert len(calls) == 1
        request = calls[0][0]
        assert urlsplit(request.url).path == '/' + endpoint
        assert parse_qs(urlsplit(request.url).query) == {'per-page': ['1']}

    @pytest.mark.parametrize('layer', ['data', 'analysis', 'plot'])
    def test_instance_filters_and_inheritance(self, http, layer):
        from openalex_analysis.analysis import WorksAnalysis
        from openalex_analysis.plot import WorksPlot
        cls = {'data': WorksData, 'analysis': WorksAnalysis, 'plot': WorksPlot}[layer]
        calls, responses = http
        responses.extend([listed([], count=50000), grouped([]), listed([], count=90000)])
        data = cls('I1', extra_filters={'publication_year': '2020-2024'})
        assert not calls  # Construction must not fetch entities.
        assert data.get_count() == 50000
        assert data.get_count_by_year().empty
        for request, _ in calls:
            assert parse_qs(urlsplit(request.url).query)['filter'] == [
                'institutions.id:I1,publication_year:2020-2024']
        equivalent = cls(extra_filters={'publication_year': '2020-2024', 'institutions.id': 'I1'})
        assert equivalent.get_count() == 50000
        assert len(calls) == 2  # Equivalent nested/dotted filters share the cache.
        assert cls().get_count() == 90000  # A separate instance represents a different query.
        assert 'filter' not in parse_qs(urlsplit(calls[-1][0].url).query)
        assert data.entities_df is None

    def test_statistics_then_explicit_loading_use_the_same_query(self, http):
        calls, responses = http
        config.n_max_entities = 1
        filters = {'publication_year': '2020-2024'}
        rows = [{'key': '2024', 'key_display_name': '2024', 'count': 50000}]
        responses.extend([listed([], count=50000), grouped(rows),
                          listed([], count=50000), listed([entity()], count=50000)])
        data = WorksData('I1', extra_filters=filters)
        assert data.entities_df is None and not calls
        assert data.get_count() == 50000
        pd.testing.assert_frame_equal(data.get_count_by_year(), pd.DataFrame(rows))
        assert data.entities_df is None
        data.load_entities_dataframe()
        assert len(data.entities_df) == 1
        assert len(calls) == 4  # Entity loading obtains a fresh preflight count.
        for request, _ in calls:
            assert parse_qs(urlsplit(request.url).query)['filter'] == [
                'institutions.id:I1,publication_year:2020-2024']
        pd.testing.assert_frame_equal(data.get_count_by_year(mode='offline'), pd.DataFrame(rows))
        assert data.get_count(mode='offline') == 50000
        assert len(data.entities_df) == 1
        cached = WorksData('I1', extra_filters=filters)
        cached.load_entities_dataframe()
        pd.testing.assert_frame_equal(data.entities_df, cached.entities_df)
        assert len(calls) == 4

    def test_explicit_loading_without_filters_uses_the_entity_cap(self, http):
        calls, responses = http
        config.n_max_entities = 1
        responses.extend([listed([], count=1000000), listed([entity()], count=1000000)])
        data = WorksData()
        assert data.database_file_path is None
        data.load_entities_dataframe()
        assert len(data.entities_df) == 1
        assert len(calls) == 2
        for request, _ in calls:
            assert 'filter' not in parse_qs(urlsplit(request.url).query)

    def test_local_parquet_file_is_loaded_only_when_requested(self, http, tmp_path):
        calls, _ = http
        path = tmp_path / 'local.parquet'
        expected = pd.DataFrame([entity()])
        expected.to_parquet(path)
        data = WorksData(database_file_path=str(path))
        assert data.entities_df is None
        data.load_entities_dataframe()
        pd.testing.assert_frame_equal(data.entities_df, expected)
        eager = WorksData(database_file_path=str(path), create_dataframe=True)
        pd.testing.assert_frame_equal(eager.entities_df, expected)
        assert not calls

    def test_analysis_loads_its_internally_created_instances(self, http):
        from openalex_analysis.analysis import WorksAnalysis
        calls, responses = http
        responses.extend([listed([], count=1), listed([
            entity(publication_year=2024, referenced_works=['https://openalex.org/W2'])])])
        data = WorksAnalysis()
        result = data.get_df_yearly_usage_of_entities_by_multiples_entities(
            count_years=[2024], entity_used_ids='W2', entity_from_ids=['I1'])
        assert result['usage_count'].tolist() == [1]
        assert result['works_count'].tolist() == [1]
        assert data.entities_df is None
        assert len(calls) == 2

    @pytest.mark.parametrize('cls, endpoint', [
        (AuthorsData, 'authors'), (InstitutionsData, 'institutions'),
        (SourcesData, 'sources'), (TopicsData, 'topics'),
        (ConceptsData, 'concepts'), (PublishersData, 'publishers'),
    ])
    def test_generic_grouping_is_inherited_by_each_endpoint(self, http, cls, endpoint):
        calls, responses = http
        rows = [{'key': 'FR', 'key_display_name': 'France', 'count': 12}]
        responses.append(grouped(rows))
        data = cls()
        fresh = data.get_group_by('country_code')
        pd.testing.assert_frame_equal(fresh, pd.DataFrame(rows))
        pd.testing.assert_frame_equal(fresh, cls().get_group_by('country_code'))
        assert len(calls) == 1
        assert urlsplit(calls[0][0].url).path == '/' + endpoint

    def test_grouping_is_unbounded_and_ignores_groups_count(self, http):
        calls, responses = http
        config.n_max_entities = 1
        rows = [{'key': f'https://openalex.org/T{i}', 'key_display_name': f'Topic {i}', 'count': i}
                for i in range(10001)]
        for start in range(0, len(rows), 200):
            cursor = f'next-{start + 200}' if start + 200 < len(rows) else None
            status, body, headers = grouped(rows[start:start + 200], cursor)
            body['meta']['groups_count'] = 1  # Deliberately not the global total.
            responses.append((status, body, headers))
        data = WorksData()
        fresh = data.get_group_by('topics.id')
        pd.testing.assert_frame_equal(fresh, pd.DataFrame(rows))
        pd.testing.assert_frame_equal(fresh, WorksData().get_group_by('topics.id'))
        assert len(calls) == 51
        for index, (request, _) in enumerate(calls):
            params = parse_qs(urlsplit(request.url).query)
            assert params['per-page'] == ['200']
            assert params['group-by'] == ['topics.id']
            assert params['cursor'] == ['*' if index == 0 else f'next-{index * 200}']
            assert 'page' not in params
        assert data.entities_df is None
        assert data.per_page == 100  # Entity-download page size is unchanged.

    @pytest.mark.parametrize('rows', [[], [
        {'key': None, 'key_display_name': None, 'count': 4},
        {'key': 'unknown', 'key_display_name': 'Unknown', 'count': 0},
        {'key': 'FR', 'key_display_name': 'France', 'count': 9},
    ]])
    def test_empty_and_unknown_groups_have_stable_cached_frames(self, http, rows):
        calls, responses = http
        responses.append(grouped(rows, total=sum(row['count'] for row in rows)))
        data = WorksData()
        field = 'authorships.countries:include_unknown'
        fresh = data.get_group_by(field)
        cached = data.get_group_by(field)
        expected = pd.DataFrame(rows, columns=['key', 'key_display_name', 'count']).astype({'count': 'int64'})
        pd.testing.assert_frame_equal(fresh, expected)
        pd.testing.assert_frame_equal(fresh, cached)
        assert len(calls) == 1
        assert parse_qs(urlsplit(calls[0][0].url).query)['group-by'] == [field]
        if rows:
            fresh.loc[0, 'count'] = 99
            pd.testing.assert_frame_equal(cached, data.get_group_by(field))

    def test_cursor_termination_can_have_an_empty_final_page(self, http):
        calls, responses = http
        rows = [{'key': 'article', 'key_display_name': 'Article', 'count': 3}]
        responses.extend([grouped(rows, 'last'), grouped([])])
        data = WorksData()
        pd.testing.assert_frame_equal(data.get_group_by('type'), pd.DataFrame(rows))
        pd.testing.assert_frame_equal(data.get_group_by('type'), pd.DataFrame(rows))
        assert len(calls) == 2

    @pytest.mark.parametrize('method, field', [
        ('get_count_by_year', 'publication_year'), ('get_count_by_type', 'type'),
        ('get_count_by_institution', 'authorships.institutions.id'),
        ('get_count_by_country', 'authorships.countries'), ('get_count_by_topic', 'topics.id'),
    ])
    def test_works_convenience_methods_share_generic_cache(self, http, method, field):
        calls, responses = http
        responses.append(grouped([]))
        data = WorksData('I1')
        fresh = getattr(data, method)(mode='refresh')
        pd.testing.assert_frame_equal(fresh, data.get_group_by(field, mode='offline'))
        assert len(calls) == 1
        params = parse_qs(urlsplit(calls[0][0].url).query)
        assert params['group-by'] == [field]
        assert params['filter'] == ['institutions.id:I1']

    @pytest.mark.parametrize('filters, expected', [
        (or_({'topics.id': ['T1', 'T2']}), 'topics.id:T1|T2'),
        ({'title': {'search': not_('ice age')}}, 'title.search:!ice age'),
    ])
    def test_queries_preserve_native_logical_filters_and_caller_inputs(self, http, filters, expected):
        calls, responses = http
        rows = [{'key': 'article', 'key_display_name': 'Article', 'count': 9}]
        responses.extend([listed([], count=9), grouped(rows, 'next'), grouped([])])
        data = WorksData(extra_filters=filters)
        assert data.get_count() == data.get_count() == 9
        pd.testing.assert_frame_equal(data.get_group_by('type'), pd.DataFrame(rows))
        pd.testing.assert_frame_equal(data.get_group_by('type'), pd.DataFrame(rows))
        assert len(calls) == 3
        for request, _ in calls:
            assert parse_qs(urlsplit(request.url).query)['filter'] == [expected]
        if 'title' in filters:
            assert filters['title']['search'].value == 'ice age'

    @pytest.mark.parametrize('operation', ['count', 'group_by'])
    def test_modes_expiration_and_disabled_cache(self, http, monkeypatch, operation):
        from openalex_analysis.data import query_cache
        calls, responses = http
        now = [1000]
        monkeypatch.setattr(query_cache, 'time', lambda: now[0])
        config.query_cache_ttl = 10
        data = WorksData()
        def query(**kwargs):
            if operation == 'count':
                return data.get_count(**kwargs)
            return data.get_group_by('type', **kwargs)['count'].sum()
        def response(count):
            return (listed([], count=count) if operation == 'count' else grouped(
                [{'key': 'article', 'key_display_name': 'Article', 'count': count}]))
        config.query_cache_mode = 'offline'
        with pytest.raises(CacheMiss):
            query()
        assert not calls
        responses.append(response(7))
        assert query(mode='auto') == 7
        assert query() == 7
        responses.append(response(8))
        assert query(mode='refresh') == 8
        now[0] += 10
        with pytest.warns(UserWarning, match='expired'):
            assert query() == 8
        responses.append(response(9))
        assert query(mode='auto') == 9
        config.query_cache_enabled = False
        with pytest.raises(CacheMiss):
            query()
        responses.extend([response(10), response(11)])
        assert query(mode='auto') == 10
        assert query(mode='auto') == 11
        assert len(calls) == 5
        config.query_cache_enabled = True
        assert query() == 9  # Disabling storage did not overwrite the old entry.

    @pytest.mark.parametrize('operation', ['count', 'group_by'])
    @pytest.mark.parametrize('status', [429, 503])
    def test_queries_use_native_pyalex_retries(self, http, monkeypatch, operation, status):
        calls, responses = http
        waits = []
        monkeypatch.setattr('urllib3.util.retry.time.sleep', waits.append)
        responses.append((status, {}, {'Retry-After': '1'}))
        data = WorksData()
        if operation == 'count':
            responses.append(listed([], count=11))
            assert data.get_count() == data.get_count() == 11
        else:
            responses.append(grouped([]))
            assert data.get_group_by('type').empty
            assert data.get_group_by('type').empty
        assert waits == [1]
        assert len(calls) == 2

    @pytest.mark.parametrize('previous_result', [False, True])
    @pytest.mark.parametrize('fallback', [False, True])
    def test_incomplete_grouping_never_replaces_complete_cache(self, http, previous_result, fallback):
        calls, responses = http
        data = WorksData()
        old_rows = [{'key': 'article', 'key_display_name': 'Article', 'count': 2}]
        if previous_result:
            responses.append(grouped(old_rows))
            original = data.get_group_by('type')
        config.max_retries = 1
        config.retry_backoff_factor = 0
        config.query_cache_stale_if_error = fallback
        responses.extend([grouped([], 'next'), (503, {}, {}), (503, {}, {})])
        if previous_result and fallback:
            with pytest.warns(UserWarning, match='fetch failed'):
                pd.testing.assert_frame_equal(original, data.get_group_by('type', mode='refresh'))
        else:
            with pytest.raises(requests.exceptions.RetryError):
                data.get_group_by('type', mode='refresh')
        assert len(calls) == 3 + int(previous_result)
        if previous_result:
            pd.testing.assert_frame_equal(original, data.get_group_by('type', mode='offline'))
        else:
            with pytest.raises(CacheMiss):
                data.get_group_by('type', mode='offline')

    @pytest.mark.parametrize('operation', ['count', 'group_by'])
    def test_credential_filters_are_rejected_before_cache_or_http(self, http, operation):
        calls, _ = http
        data = WorksData()
        data.extra_filters = {'authorships': {'api_key': 'private-test-key'}}
        with pytest.raises(ValueError, match='credentials'):
            if operation == 'count':
                data.get_count()
            else:
                data.get_group_by('type')
        assert not calls
        assert not Path(config.query_cache_path).exists()

    @pytest.mark.parametrize('cls, ids, expected', [
        (WorksData, ['W1', 'https://openalex.org/W2'], 'ids.openalex:W1|W2'),
        (InstitutionsData, ['I1', 'I2'], 'ids.openalex:I1|I2'),
        (WorksData, ['10.1234/Example', 'https://doi.org/10.1234/other'], 'doi:10.1234/example|10.1234/other'),
    ])
    def test_id_lists_scope_counts_and_groups(self, http, cls, ids, expected):
        calls, responses = http
        data = cls(entities_from_id_list=ids)
        assert not calls
        responses.extend([listed([], count=2), grouped([])])
        assert data.get_count() == data.get_count() == 2
        assert data.get_group_by('type').empty
        assert data.get_group_by('type').empty
        assert data.entities_df is None
        assert len(calls) == 2
        for request, _ in calls:
            assert parse_qs(urlsplit(request.url).query)['filter'] == [expected]

        prefix = 'W' if cls is WorksData else 'I'
        records = [entity(f'{prefix}{i}') for i in (1, 2)]
        if expected.startswith('doi:'):
            for record, doi in zip(records, ['10.1234/example', '10.1234/other']):
                record['doi'] = 'https://doi.org/' + doi
        responses.append(listed(records))
        data.load_entities_dataframe()
        assert data.entities_df['id'].tolist() == [record['id'] for record in records]
        assert data.get_count(mode='offline') == 2
        assert len(calls) == 3

    def test_empty_id_lists_have_no_matching_entities(self, http):
        calls, _ = http
        data = WorksData(entities_from_id_list=[])
        assert data.entities_df is None
        assert data.get_count() == data.get_count(mode='offline') == 0
        assert data.get_group_by('type').empty
        assert data.get_group_by('type', mode='offline').empty
        data.load_entities_dataframe()
        assert data.entities_df.empty
        assert not calls

    def test_unsupported_id_lists_do_not_query_the_whole_corpus(self, http):
        calls, _ = http
        data = WorksData(entities_from_id_list=['not-an-id'])
        with pytest.raises(ValueError, match='ID pattern'):
            data.get_count()
        with pytest.raises(ValueError, match='ID pattern'):
            data.get_group_by('type')
        assert not calls

    @pytest.mark.parametrize('field', [None, '', '   '])
    def test_missing_grouping_field_does_not_request_entity_records(self, http, field):
        calls, _ = http
        with pytest.raises(ValueError, match='grouping field'):
            WorksData().get_group_by(field)
        assert not calls
