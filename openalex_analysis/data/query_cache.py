"""Persistent JSON cache for counts and grouped queries; no HTTP implementation."""

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sqlite3
from time import monotonic, sleep, time
from urllib.parse import parse_qsl, urlsplit, urlunsplit
import warnings

from pyalex.api import BaseOpenAlex, OpenAlexResponseList, QueryError
from requests.exceptions import RequestException

from .entities_data import config, _validate_filters


SCHEMA_VERSION = 1
OPERATIONS = {'count', 'group_by', 'group_by_all'}
MODES = {'auto', 'refresh', 'offline'}
AUTH_FIELDS = {'apikey', 'authorization', 'accesstoken'}


class CacheMiss(LookupError):
    """An offline query has no usable cached result."""


def _auth_field(key):
    return key.rsplit('.', 1)[-1].lower().replace('_', '').replace('-', '') in AUTH_FIELDS


def _dumps(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=False)


def _base_url(value):
    parts = urlsplit(value)
    if (parts.scheme not in {'http', 'https'} or not parts.hostname or
            parts.username is not None or parts.password is not None or parts.query or parts.fragment):
        raise ValueError('Cache API base URL must be HTTP(S), without credentials, query or fragment.')
    host = parts.hostname.lower()
    if ':' in host:
        host = '[' + host + ']'
    if parts.port is not None and (parts.scheme, parts.port) not in {('http', 80), ('https', 443)}:
        host += ':' + str(parts.port)
    return urlunsplit((parts.scheme.lower(), host, parts.path.rstrip('/'), '', ''))


def _ordered(value):
    """Sort filter mappings without losing PyAlex logical types."""
    if isinstance(value, dict):
        return type(value)((key, _ordered(value[key])) for key in sorted(value))
    if isinstance(value, list):
        return [_ordered(item) for item in value]
    return value


def _descriptor(base_url, endpoint, operation, parameters):
    if operation not in OPERATIONS:
        raise ValueError('Query cache operation must be count, group_by or group_by_all.')
    if not isinstance(endpoint, str) or not endpoint.strip('/') or any(c in endpoint for c in '?#:@'):
        raise ValueError('Query cache endpoint must be a path without query parameters or fragments.')
    aliases = {'group_by': 'group-by', 'per_page': 'per-page'}
    params = {}
    for key, value in parameters.items():
        if _auth_field(key) or key in {'email', 'mailto'}:
            continue
        key = aliases.get(key, key)
        if key in params:
            raise ValueError('Specify each query parameter once, without duplicate aliases.')
        params[key] = value
    _validate_filters(params)
    # PyAlex owns filter/logical-expression serialization. No HTTP request is made.
    params = deepcopy(params)
    if isinstance(params.get('filter'), dict):
        params['filter'] = _ordered(params['filter'])
    query = BaseOpenAlex(params=params).url
    return {'schema_version': SCHEMA_VERSION, 'base_url': _base_url(base_url),
            'endpoint': endpoint.strip('/'), 'operation': operation,
            'parameters': dict(parse_qsl(urlsplit(query).query, keep_blank_values=True))}


def _expiry_cutoff():
    duration = config.query_cache_ttl
    if type(duration) not in (int, float) or not math.isfinite(duration) or duration < 0:
        raise ValueError('config.query_cache_ttl must be finite non-negative seconds.')
    return time() - duration


def _invalid_constant(value):
    raise ValueError('Non-finite JSON constant.')


class QueryCache:
    """SQLite cache for JSON query results, separate from entity Parquet files.

    get()/set()/invalidate() identify a query by endpoint, operation and parameters
    (PyAlex-style ``filter`` dictionaries and ``group_by``/``group-by`` parameters).
    Filter dictionary order is normalized before PyAlex serializes parameters,
    preserving PyAlex logical expressions, list order and sort priority.

    get_or_fetch() implements auto/refresh/offline using a zero-argument callback.
    The group_by operation identifies one response page; group_by_all identifies
    a complete cursor scan, so the two cannot satisfy each other's cache reads.
    get_or_fetch_pages() stores pages only after the supplied iterator finishes
    successfully. The caller must supply an unbounded paginator (n_max=None).
    Native PyAlex grouped pages become JSON dictionaries with meta and group_by;
    already normalized JSON pages pass through unchanged.
    No network calls occur inside this class. Offline mode warns on stale reads.

    SQLite stores only retrieval timestamps. Freshness and cleanup use the current
    config.query_cache_ttl duration in seconds for every query. Limits apply to row
    count and serialized query/result bytes, not SQLite/WAL filesystem overhead.
    Expired entries remain available for fallback until cleanup or eviction.
    Settings come from config; only the database path can be overridden at construction.
    Connections are short-lived and local to each operation/thread.
    """

    def __init__(self, path=None):
        self.path = Path(path if path is not None else config.query_cache_path).expanduser()
        if str(self.path) == ':memory:':
            raise ValueError('QueryCache requires a persistent SQLite file path.')
        self.path = self.path.resolve()
        _expiry_cutoff()
        if config.query_cache_mode not in MODES:
            raise ValueError('Query cache mode must be auto, refresh or offline.')
        for name in ('query_cache_max_entries', 'query_cache_max_size_bytes', 'query_cache_busy_timeout_ms'):
            value = config[name]
            if type(value) is not int or value < 0:
                raise ValueError('Query cache limits and busy timeout must be non-negative integers.')
        if config.query_cache_enabled:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._connection() as db:
                # Simultaneous first opens can bypass SQLite's busy timeout here.
                deadline = monotonic() + config.query_cache_busy_timeout_ms / 1000
                while True:
                    try:
                        db.execute('PRAGMA journal_mode=WAL')
                        break
                    except sqlite3.OperationalError as error:
                        if str(error) != 'database is locked' or monotonic() >= deadline:
                            raise
                        sleep(0.01)
                db.execute('BEGIN IMMEDIATE')
                version = db.execute('PRAGMA user_version').fetchone()[0]
                if version not in (0, SCHEMA_VERSION):
                    raise sqlite3.DatabaseError('Unsupported query cache schema version.')
                db.execute('''CREATE TABLE IF NOT EXISTS query_cache (
                    query_hash TEXT PRIMARY KEY, base_url TEXT NOT NULL,
                    endpoint TEXT NOT NULL, operation TEXT NOT NULL,
                    parameters_json TEXT NOT NULL, result_json TEXT NOT NULL,
                    retrieved_at REAL NOT NULL,
                    schema_version INTEGER NOT NULL, size_bytes INTEGER NOT NULL)''')
                db.execute('CREATE INDEX IF NOT EXISTS query_cache_retrieved ON query_cache(retrieved_at)')
                db.execute(f'PRAGMA user_version={SCHEMA_VERSION}')

    @contextmanager
    def _connection(self):
        db = sqlite3.connect(self.path, timeout=config.query_cache_busy_timeout_ms / 1000)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _query(self, endpoint, operation, parameters, base_url):
        return _descriptor(config.openalex_url if base_url is None else base_url,
                           endpoint, operation, parameters)

    def make_key(self, endpoint, operation, parameters, *, base_url=None):
        """Return a SHA-256 key without persisting a query or authentication data."""
        return self._key(self._query(endpoint, operation, parameters, base_url))

    @staticmethod
    def _key(query):
        return hashlib.sha256(_dumps(query).encode()).hexdigest()

    def _read(self, key):
        """Read and decode one entry, retaining its date for freshness decisions."""
        with self._connection() as db:
            row = db.execute('''SELECT result_json, retrieved_at, schema_version
                FROM query_cache WHERE query_hash=?''', (key,)).fetchone()
        if row is None:
            return None
        try:
            result, retrieved, version = row
            if version != SCHEMA_VERSION or not math.isfinite(retrieved):
                raise ValueError('Invalid query cache record.')
            result = json.loads(result, parse_constant=_invalid_constant)
        except (ValueError, TypeError, OverflowError):
            warnings.warn('Ignoring an invalid query cache entry.', UserWarning, stacklevel=2)
            return None
        return result, retrieved

    def get(self, endpoint, operation, parameters, *, base_url=None, allow_stale=False):
        """Return decoded JSON, or None on a miss, expiry or invalid record."""
        if not config.query_cache_enabled:
            return None
        entry = self._read(self.make_key(endpoint, operation, parameters, base_url=base_url))
        if entry is None:
            return None
        result, retrieved = entry
        if not allow_stale and retrieved <= _expiry_cutoff():
            return None
        return result

    def set(self, endpoint, operation, parameters, result, *, base_url=None):
        """Atomically replace one complete JSON result and enforce storage limits."""
        if not config.query_cache_enabled:
            return
        query = self._query(endpoint, operation, parameters, base_url)
        self._write(query, self._key(query), result)

    def _write(self, query, key, result):
        _validate_filters(result)
        encoded = _dumps(result)
        params = _dumps(query['parameters'])
        now = time()
        size = len(_dumps(query).encode()) + len(encoded.encode())
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''INSERT OR REPLACE INTO query_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
                       (key, query['base_url'], query['endpoint'], query['operation'], params, encoded,
                        now, SCHEMA_VERSION, size))
            self._evict(db)

    def _evict(self, db):
        max_entries, max_size = config.query_cache_max_entries, config.query_cache_max_size_bytes
        count, total_size = db.execute('SELECT count(*), coalesce(sum(size_bytes), 0) FROM query_cache').fetchone()
        if count <= max_entries and total_size <= max_size:
            return
        entries = db.execute('SELECT query_hash, size_bytes FROM query_cache ORDER BY retrieved_at DESC, query_hash').fetchall()
        size = 0
        kept = 0
        remove = []
        for key, entry_size in entries:
            if kept >= max_entries or size + entry_size > max_size:
                remove.append((key,))
            else:
                kept += 1
                size += entry_size
        db.executemany('DELETE FROM query_cache WHERE query_hash=?', remove)

    def get_or_fetch(self, endpoint, operation, parameters, fetch, *, base_url=None,
                     mode=None, stale_if_error=None):
        """Apply cache policy; optional fallback handles only request and PyAlex query errors."""
        mode = config.query_cache_mode if mode is None else mode
        if mode not in MODES:
            raise ValueError('Query cache mode must be auto, refresh or offline.')
        if not config.query_cache_enabled:
            if mode == 'offline':
                raise CacheMiss('No usable offline query cache entry is available.')
            return fetch()
        # PyAlex can mutate filter expressions while fetching; freeze identity first.
        query = self._query(endpoint, operation, parameters, base_url)
        key = self._key(query)
        fallback = config.query_cache_stale_if_error if stale_if_error is None else stale_if_error
        entry = self._read(key) if mode != 'refresh' or fallback else None
        if entry is not None:
            cached, retrieved = entry
            expired = retrieved <= _expiry_cutoff()
            if mode == 'offline':
                if expired:
                    warnings.warn('Using an expired query cache entry in offline mode.', UserWarning, stacklevel=2)
                return cached
            if mode == 'auto' and not expired:
                return cached
        if mode == 'offline':
            raise CacheMiss('No usable offline query cache entry is available.')
        try:
            result = fetch()
        except (RequestException, QueryError):
            if not fallback or entry is None:
                raise
            warnings.warn('Query fetch failed; using the previously cached result.', UserWarning, stacklevel=2)
            return cached
        self._write(query, key, result)
        return result

    def get_or_fetch_pages(self, endpoint, parameters, fetch_pages, **kwargs):
        """Return JSON pages with metadata, caching only after the iterator finishes."""
        def fetch():
            return [{'meta': page.meta, 'group_by': list(page)}
                    if isinstance(page, OpenAlexResponseList) else page
                    for page in fetch_pages()]
        return self.get_or_fetch(endpoint, 'group_by_all', parameters,
                                 fetch, **kwargs)

    def invalidate(self, endpoint, operation, parameters, *, base_url=None):
        """Delete one query; return the number of deleted entries."""
        if not config.query_cache_enabled:
            return 0
        key = self.make_key(endpoint, operation, parameters, base_url=base_url)
        with self._connection() as db:
            return db.execute('DELETE FROM query_cache WHERE query_hash=?', (key,)).rowcount

    def clear(self):
        """Delete all query entries without touching entity Parquet files."""
        if not config.query_cache_enabled:
            return 0
        with self._connection() as db:
            return db.execute('DELETE FROM query_cache').rowcount

    def cleanup(self, *, expired=True, compact=False):
        """Remove expired/obsolete entries, enforce limits, optionally reclaim disk space."""
        if not config.query_cache_enabled:
            return 0
        with self._connection() as db:
            db.execute('BEGIN IMMEDIATE')
            before = db.execute('SELECT count(*) FROM query_cache').fetchone()[0]
            db.execute('DELETE FROM query_cache WHERE schema_version!=?', (SCHEMA_VERSION,))
            if expired:
                db.execute('DELETE FROM query_cache WHERE retrieved_at<=?', (_expiry_cutoff(),))
            self._evict(db)
            removed = before - db.execute('SELECT count(*) FROM query_cache').fetchone()[0]
        if compact:
            with self._connection() as db:
                db.execute('VACUUM')
                db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        return removed
