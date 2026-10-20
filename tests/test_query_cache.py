"""SQLite query-cache behavior; no OpenAlex access or entity downloads."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import sqlite3
from threading import Barrier, Event

import pytest
from pyalex.api import OpenAlexResponseList, QueryError
from requests.exceptions import ConnectionError, HTTPError, RequestException, Timeout

from openalex_analysis.data import CacheMiss, QueryCache, config, load_config_from_file
from openalex_analysis.data import query_cache as module
from openalex_analysis.data.entities_data import set_default_config


PARAMS = {'filter': {'institutions': {'id': 'I1'}}, 'group_by': 'publication_year'}


def page(key='2020', cursor=None):
    return {'meta': {'count': 7, 'next_cursor': cursor},
            'group_by': [{'key': key, 'key_display_name': key, 'count': 7}]}


@pytest.fixture(autouse=True)
def isolated_config(monkeypatch):
    from pyalex import config as pyalex_config
    saved, saved_pyalex = config.copy(), pyalex_config.copy()
    monkeypatch.delenv('OPENALEX_API_KEY', raising=False)
    set_default_config()
    yield
    config.clear()
    for key, value in saved.items():
        setattr(config, key, value)
    pyalex_config.clear()
    pyalex_config.update(saved_pyalex)


@pytest.fixture
def clock(monkeypatch):
    now = [datetime(2026, 6, 1, tzinfo=timezone.utc).timestamp()]
    monkeypatch.setattr(module, 'time', lambda: now[0])
    return now


@pytest.fixture
def cache(tmp_path, clock):
    return QueryCache(tmp_path / 'queries.sqlite3')


def test_canonical_nested_filters_aliases_and_url(cache):
    first = {'filter': {'publication_year': 2020, 'authorships': {'institutions': {'id': 'I1'}}},
             'group-by': 'publication_year', 'per-page': 100}
    second = {'per_page': 100, 'group_by': 'publication_year',
              'filter': {'authorships.institutions.id': 'I1', 'publication_year': 2020}}
    key = cache.make_key('/works/', 'group_by', first, base_url='HTTPS://API.OpenAlex.org:443/')
    assert key == cache.make_key('works', 'group_by', second, base_url='https://api.openalex.org')
    assert len(key) == 64
    assert int(key, 16) >= 0


@pytest.mark.parametrize('parameters', [
    {'filter': {'publication_year': [2020, 2021]}},
    {'filter': {'publication_year': '2020|2021'}},
    {'group_by': 'type'}, {'cursor': 'next'}, {'sort': {'key': 'desc'}},
    {'select': ['id', 'count']}, {'per_page': 10}, {'sample': 5}, {'seed': 2},
    {'corpus': 'all'}, {'future_parameter': True},
])
def test_all_result_parameters_affect_keys(cache, parameters):
    assert cache.make_key('works', 'count', {}) != cache.make_key('works', 'count', parameters)


def test_keys_keep_order_and_operation_semantics(cache):
    key = lambda params: cache.make_key('works', 'count', params)
    assert key({'filter': {'topics.id': ['T1', 'T2']}}) != key({'filter': {'topics.id': ['T2', 'T1']}})
    assert key({'sort': {'cited_by_count': 'desc', 'publication_date': 'desc'}}) != key(
        {'sort': {'publication_date': 'desc', 'cited_by_count': 'desc'}})
    assert key({'filter': {'publication_year': 2020}}) == key({'filter': {'publication_year': '2020'}})
    assert cache.make_key('works', 'group_by', PARAMS) != cache.make_key('works', 'group_by_all', PARAMS)
    assert cache.make_key('works', 'count', {}) != cache.make_key('authors', 'count', {})
    assert cache.make_key('works', 'count', {}) != cache.make_key('works', 'count', {}, base_url='https://example.org/api')
    assert key({'cursor': None}) == key({})


def test_pyalex_logical_filters_keep_their_semantics_without_mutation(cache):
    from pyalex.api import not_, or_
    both = {'filter': {'topics.id': ['T1', 'T2']}}
    either = {'filter': or_({'topics.id': ['T1', 'T2']})}
    assert cache.make_key('works', 'count', both) != cache.make_key('works', 'count', either)
    expression = not_('ice age')
    params = {'filter': {'title.search': expression}}
    assert cache.make_key('works', 'count', params) == cache.make_key('works', 'count', params)
    assert expression.value == 'ice age'


def test_credentials_never_persist_or_change_key(cache):
    secret = 'private-test-api-key'
    params = {'api_key': secret, 'Authorization': 'Bearer ' + secret, 'filter': {'publication_year': 2020}}
    public = {'filter': {'publication_year': 2020}}
    assert cache.make_key('works', 'count', params) == cache.make_key('works', 'count', public)
    cache.set('works', 'count', params, 7)
    with sqlite3.connect(cache.path) as db:
        row = db.execute('SELECT * FROM query_cache').fetchone()
    assert secret not in repr(row)
    assert secret.encode() not in cache.path.read_bytes()
    for base in ['https://user:password@example.org', 'https://example.org?api_key=' + secret]:
        with pytest.raises(ValueError, match='credentials'):
            cache.make_key('works', 'count', public, base_url=base)
    with pytest.raises(ValueError, match='credentials'):
        cache.set('works', 'count', {'filter': {'api_key': secret}}, 1)
    with pytest.raises(ValueError, match='credentials'):
        cache.set('works', 'count', public, {'meta': {'count': 1}, 'api_key': secret})


def test_record_schema_and_database_reopening(cache, clock):
    result = {'meta': {'count': 0, 'cost_usd': 0}, 'results': []}
    cache.set('works', 'count', {}, result)
    with sqlite3.connect(cache.path) as db:
        db.row_factory = sqlite3.Row
        row = db.execute('SELECT * FROM query_cache').fetchone()
        assert db.execute('PRAGMA journal_mode').fetchone()[0] == 'wal'
    assert row['query_hash'] == cache.make_key('works', 'count', {})
    assert row['endpoint'] == 'works' and row['operation'] == 'count'
    assert json.loads(row['parameters_json']) == {}
    assert json.loads(row['result_json']) == result
    assert row['retrieved_at'] == clock[0]
    assert 'expires_at' not in row.keys()
    assert row['schema_version'] == module.SCHEMA_VERSION
    assert 'complete' not in row.keys()  # Complete fetches are committed atomically.
    reopened = QueryCache(cache.path)
    assert reopened.get('works', 'count', {}) == result
    with reopened._connection() as db:
        assert db.execute('PRAGMA busy_timeout').fetchone()[0] == 5000


def test_auto_hit_zero_count_and_independent_decoding(cache):
    calls = []
    def fetch():
        calls.append(1)
        return 0
    assert cache.get_or_fetch('works', 'count', {}, fetch) == 0
    assert cache.get_or_fetch('works', 'count', {}, fetch) == 0
    assert calls == [1]
    original = page()
    cache.set('works', 'group_by', PARAMS, original)
    cached = cache.get('works', 'group_by', PARAMS)
    cached['group_by'].clear()
    assert cache.get('works', 'group_by', PARAMS) == original


def test_expiration_refresh_and_offline(cache, clock):
    config.query_cache_ttl = 10
    cache.set('works', 'count', {}, 1)
    clock[0] += 10
    assert cache.get('works', 'count', {}) is None
    assert cache.get('works', 'count', {}, allow_stale=True) == 1
    def no_fetch():
        pytest.fail('Offline mode called the API callback')
    with pytest.warns(UserWarning, match='expired'):
        assert cache.get_or_fetch('works', 'count', {}, no_fetch, mode='offline') == 1
    with pytest.raises(CacheMiss):
        cache.get_or_fetch('authors', 'count', {}, no_fetch, mode='offline')
    assert cache.get_or_fetch('works', 'count', {}, lambda: 2, mode='auto') == 2
    assert cache.get_or_fetch('works', 'count', {}, lambda: 3, mode='refresh') == 3
    assert cache.get_or_fetch('works', 'count', {}, no_fetch, mode='offline') == 3


@pytest.mark.parametrize('use_config', [False, True])
@pytest.mark.parametrize('error_type', [RequestException, ConnectionError, HTTPError, Timeout, QueryError])
def test_stale_fallback_preserves_errors_and_warns_without_secrets(cache, clock, use_config, error_type):
    config.query_cache_ttl = 1
    cache.set('works', 'count', {}, 7)
    clock[0] += 2
    error = error_type('api_key=never-print-this')
    def failed():
        raise error
    with pytest.raises(error_type) as caught:
        cache.get_or_fetch('works', 'count', {}, failed)
    assert caught.value is error
    config.query_cache_stale_if_error = use_config
    options = {} if use_config else {'stale_if_error': True}
    with pytest.warns(UserWarning, match='fetch failed') as messages:
        assert cache.get_or_fetch('works', 'count', {}, failed, **options) == 7
    assert all('never-print-this' not in str(message.message) for message in messages)
    with pytest.raises(error_type):
        cache.get_or_fetch('authors', 'count', {}, failed, **options)
    with pytest.raises(ValueError):
        cache.get_or_fetch('works', 'count', {}, lambda: float('nan'), **options)


@pytest.mark.parametrize('mode', ['auto', 'refresh'])
@pytest.mark.parametrize('error_type', [TypeError, ValueError, RuntimeError])
def test_stale_fallback_does_not_hide_callback_bugs(cache, clock, mode, error_type):
    config.query_cache_ttl = 1
    cache.set('works', 'count', {}, 7)
    clock[0] += 2
    error = error_type('Local callback bug')
    def failed():
        raise error
    with pytest.raises(error_type) as caught:
        cache.get_or_fetch('works', 'count', {}, failed, mode=mode, stale_if_error=True)
    assert caught.value is error
    assert cache.get('works', 'count', {}, allow_stale=True) == 7


def test_disabled_cache_never_creates_database_or_fetches_offline(tmp_path):
    path = tmp_path / 'absent' / 'cache.sqlite3'
    config.query_cache_enabled = False
    cache = QueryCache(path)
    calls = []
    def fetch():
        calls.append(1)
        return 7
    assert cache.get_or_fetch('works', 'count', {}, fetch) == 7
    assert cache.get_or_fetch('works', 'count', {}, fetch) == 7
    with pytest.raises(CacheMiss):
        cache.get_or_fetch('works', 'count', {}, fetch, mode='offline')
    assert calls == [1, 1]
    assert not path.parent.exists()
    assert cache.cleanup() == cache.clear() == cache.invalidate('works', 'count', {}) == 0


@pytest.mark.parametrize('duration', [1, 10.5, 86400, 30 * 86400])
def test_entries_expire_at_configured_age(cache, clock, duration):
    config.query_cache_ttl = duration
    cache.set('works', 'count', {}, 1)
    clock[0] += duration - 0.5
    assert cache.get('works', 'count', {}) == 1
    clock[0] += 0.5
    assert cache.get('works', 'count', {}) is None


def test_zero_duration_expires_immediately(cache):
    config.query_cache_ttl = 0
    cache.set('works', 'count', {}, 1)
    assert cache.get('works', 'count', {}) is None
    assert cache.cleanup() == 1


def test_duration_changes_apply_to_existing_entries_and_cleanup(cache, clock):
    config.query_cache_ttl = 10
    cache.set('works', 'count', {}, 7)
    clock[0] += 20
    assert cache.get('works', 'count', {}) is None
    config.query_cache_ttl = 30
    assert cache.get('works', 'count', {}) == 7
    assert QueryCache(cache.path).get('works', 'count', {}) == 7
    assert cache.cleanup() == 0
    config.query_cache_ttl = 5
    assert cache.cleanup() == 1


def test_ttl_and_mode_configuration_loaded_from_toml(tmp_path, clock):
    path = tmp_path / 'settings.toml'
    database = tmp_path / 'cache.sqlite3'
    path.write_text(f'query_cache_path = "{database}"\nquery_cache_mode = "offline"\n'
                    'query_cache_max_entries = 3\nquery_cache_max_size_bytes = 500\n'
                    'query_cache_busy_timeout_ms = 1234\nquery_cache_stale_if_error = true\n'
                    'query_cache_ttl = 2\n')
    load_config_from_file(str(path))
    cache = QueryCache()
    assert cache.path == database
    assert config.query_cache_stale_if_error
    assert config.query_cache_max_entries == 3 and config.query_cache_max_size_bytes == 500
    with pytest.raises(CacheMiss):
        cache.get_or_fetch('works', 'count', {}, lambda: pytest.fail('Offline mode called the API'))
    with cache._connection() as db:
        assert db.execute('PRAGMA busy_timeout').fetchone()[0] == 1234
    params = {'filter': {'publication_year': 2024}}
    cache.set('works', 'count', params, 7)
    clock[0] += 2
    assert cache.get('works', 'count', params) is None
    path.write_text(path.read_text().replace('query_cache_ttl = 2', 'query_cache_ttl = 50'))
    load_config_from_file(str(path))
    assert cache.get('works', 'count', params) == 7
    clock[0] += 48
    assert cache.get('works', 'count', params) is None
    assert config.n_max_entities == 10000  # ordinary defaults still load


@pytest.mark.parametrize('native_pages', [False, True])
def test_all_grouped_pages_are_stored_without_losing_metadata(cache, native_pages):
    expected = [page('2020', 'next'), page('2021')]
    calls = []
    def fetch_pages():
        calls.append(1)
        for result in expected:
            yield OpenAlexResponseList(result['group_by'], result['meta']) if native_pages else result
    assert cache.get_or_fetch_pages('works', PARAMS, fetch_pages) == expected
    assert cache.get_or_fetch_pages('works', PARAMS, fetch_pages) == expected
    assert calls == [1]
    assert cache.get('works', 'group_by', PARAMS) is None  # page vs full aggregation


def test_fetch_failure_after_a_page_does_not_publish_partial_results(cache):
    original = [page()]
    cache.set('works', 'group_by_all', PARAMS, original)
    def interrupted():
        yield page(cursor='next')
        raise RuntimeError('network interrupted')
    with pytest.raises(RuntimeError):
        cache.get_or_fetch_pages('works', PARAMS, interrupted, mode='refresh')
    assert cache.get('works', 'group_by_all', PARAMS) == original
    with pytest.raises(RuntimeError):
        cache.get_or_fetch_pages('authors', PARAMS, interrupted)
    assert cache.get('authors', 'group_by_all', PARAMS) is None


def test_readers_see_old_result_until_complete_refresh(cache):
    original, replacement = [page()], [page('2021', 'next'), page('2022')]
    cache.set('works', 'group_by_all', PARAMS, original)
    fetching, finish = Event(), Event()
    def fetch_pages():
        yield replacement[0]
        fetching.set()
        assert finish.wait(5)
        yield replacement[1]
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(cache.get_or_fetch_pages, 'works', PARAMS, fetch_pages, mode='refresh')
        try:
            assert fetching.wait(5)
            assert cache.get('works', 'group_by_all', PARAMS) == original
        finally:
            finish.set()
        assert result.result(timeout=5) == replacement
    assert cache.get('works', 'group_by_all', PARAMS) == replacement


def test_concurrent_instances_and_threads(tmp_path, clock):
    path = tmp_path / 'shared.sqlite3'
    cache = QueryCache(path)
    def worker(index):
        local = QueryCache(path)
        for number in range(10):
            params = {'worker': index, 'number': number}
            local.set('works', 'count', params, number)
            assert local.get('works', 'count', params) == number
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(worker, range(8)))
    with sqlite3.connect(cache.path) as db:
        assert db.execute('SELECT count(*) FROM query_cache').fetchone()[0] == 80


def test_concurrent_first_open(tmp_path):
    path = tmp_path / 'new.sqlite3'
    start = Barrier(6)
    def worker(index):
        start.wait(timeout=5)
        cache = QueryCache(path)
        cache.set('works', 'count', {'index': index}, index)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(worker, range(6)))
    cache = QueryCache(path)
    assert [cache.get('works', 'count', {'index': index}) for index in range(6)] == list(range(6))


def test_busy_timeout_and_wal_readers(cache):
    cache.set('works', 'count', {}, 7)
    locked = sqlite3.connect(cache.path)
    locked.execute('BEGIN IMMEDIATE')
    try:
        config.query_cache_busy_timeout_ms = 0
        with pytest.raises(sqlite3.OperationalError, match='locked'):
            cache.set('works', 'count', {}, 8)
        assert cache.get('works', 'count', {}) == 7
        config.query_cache_busy_timeout_ms = 5000
        with ThreadPoolExecutor(max_workers=1) as pool:
            result = pool.submit(cache.set, 'works', 'count', {}, 9)
            locked.rollback()
            result.result(timeout=5)
    finally:
        locked.close()
    assert cache.get('works', 'count', {}) == 9


@pytest.mark.parametrize('column, value', [
    ('result_json', 'not JSON'), ('result_json', 'NaN'), ('schema_version', 999),
    ('retrieved_at', 'invalid'), ('retrieved_at', float('inf')),
])
def test_invalid_entries_are_misses_and_can_be_repaired(cache, column, value):
    cache.set('works', 'count', {}, 7)
    with sqlite3.connect(cache.path) as db:
        db.execute(f'UPDATE query_cache SET {column}=?', (value,))
    with pytest.warns(UserWarning, match='invalid query cache entry'):
        assert cache.get('works', 'count', {}) is None
    cache.set('works', 'count', {}, 8)
    assert cache.get('works', 'count', {}) == 8


def test_corrupted_database_is_reported_without_destroying_it(tmp_path):
    path = tmp_path / 'broken.sqlite3'
    original = b'not a SQLite database'
    path.write_bytes(original)
    with pytest.raises(sqlite3.DatabaseError):
        QueryCache(path)
    assert path.read_bytes() == original


def test_future_schema_version_is_not_overwritten(tmp_path):
    path = tmp_path / 'future.sqlite3'
    with sqlite3.connect(path) as db:
        db.execute('PRAGMA user_version=999')
    with pytest.raises(sqlite3.DatabaseError, match='Unsupported'):
        QueryCache(path)
    with sqlite3.connect(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 999


def test_relative_path_remains_valid_when_working_directory_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cache = QueryCache('relative.sqlite3')
    cache.set('works', 'count', {}, 7)
    other = tmp_path / 'other'
    other.mkdir()
    monkeypatch.chdir(other)
    assert cache.get('works', 'count', {}) == 7


def test_in_memory_database_is_rejected():
    with pytest.raises(ValueError, match='persistent'):
        QueryCache(':memory:')


def test_cache_stores_json_without_interpreting_response_fields(cache):
    result = {'group_by': [{'future_bucket_field': 'value'}], 'future_metadata': [1, True, None]}
    cache.set('works', 'group_by', PARAMS, result)
    assert QueryCache(cache.path).get('works', 'group_by', PARAMS) == result


def test_cleanup_invalidation_and_limits(tmp_path, clock):
    config.query_cache_ttl = 10
    config.query_cache_max_entries = 2
    cache = QueryCache(tmp_path / 'limits.sqlite3')
    for index in range(3):
        cache.set('works', 'count', {'index': index}, index)
        clock[0] += 1
    assert cache.get('works', 'count', {'index': 0}) is None
    assert cache.invalidate('works', 'count', {'index': 1}) == 1
    assert cache.invalidate('works', 'count', {'index': 1}) == 0
    clock[0] += 10
    assert cache.cleanup() == 1
    assert cache.cleanup(compact=True) == 0
    assert cache.clear() == 0
    cache.set('works', 'count', {}, 7)
    assert cache.clear() == 1


def test_size_limit_skips_oversize_entry_without_purging_small_entries(tmp_path, clock):
    config.query_cache_max_size_bytes = 500
    cache = QueryCache(tmp_path / 'size.sqlite3')
    cache.set('works', 'count', {}, 7)
    clock[0] += 1
    cache.set('works', 'group_by', PARAMS, page('x' * 1000))
    assert cache.get('works', 'group_by', PARAMS) is None
    assert cache.get('works', 'count', {}) == 7
    with sqlite3.connect(cache.path) as db:
        assert db.execute('SELECT sum(size_bytes) FROM query_cache').fetchone()[0] <= 500


def test_write_and_eviction_roll_back_together(tmp_path, clock):
    config.query_cache_max_entries = 1
    cache = QueryCache(tmp_path / 'transaction.sqlite3')
    cache.set('works', 'count', {'old': True}, 7)
    with sqlite3.connect(cache.path) as db:
        db.execute("CREATE TRIGGER no_eviction BEFORE DELETE ON query_cache BEGIN SELECT RAISE(ABORT, 'blocked'); END")
    clock[0] += 1
    with pytest.raises(sqlite3.IntegrityError, match='blocked'):
        cache.set('works', 'count', {'new': True}, 8)
    assert cache.get('works', 'count', {'old': True}) == 7
    assert cache.get('works', 'count', {'new': True}) is None


@pytest.mark.parametrize('name, value', [('query_cache_mode', 'invalid'),
                                       ('query_cache_max_entries', -1),
                                       ('query_cache_busy_timeout_ms', -1)])
def test_invalid_configuration_fails_clearly(tmp_path, name, value):
    setattr(config, name, value)
    with pytest.raises(ValueError):
        QueryCache(tmp_path / 'invalid.sqlite3')


@pytest.mark.parametrize('duration', [-1, True, float('inf'), float('nan'), '10', {'recent': 1}])
def test_invalid_duration_configuration_fails_clearly(tmp_path, duration):
    config.query_cache_ttl = duration
    with pytest.raises(ValueError, match='config.query_cache_ttl'):
        QueryCache(tmp_path / 'invalid.sqlite3')
