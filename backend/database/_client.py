import hashlib
import json
import os
import sqlite3
import threading
import uuid
from copy import deepcopy

# ---------------------------------------------------------------------------
# Lazy import of firestore — only imported when actually used.
# This avoids the credentials check at module load time when
# SERVICE_ACCOUNT_JSON is not set.
# ---------------------------------------------------------------------------

def _get_firestore():
    from google.cloud import firestore
    return firestore


def _get_firestore_client():
    sa_json = os.environ.get('SERVICE_ACCOUNT_JSON')
    if not sa_json:
        return None
    service_account_info = json.loads(sa_json)
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)
    firestore = _get_firestore()
    return firestore.Client()


# ---------------------------------------------------------------------------
# Local SQLite fallback — used when SERVICE_ACCOUNT_JSON is not set.
# All database/ modules import from _client; this class provides a
# minimal document-oriented interface so the rest of the backend can
# start without Firebase.
# ---------------------------------------------------------------------------

_local_db: sqlite3.Connection | None = None
_local_lock = threading.Lock()


def _local_db_conn() -> sqlite3.Connection:
    global _local_db
    if _local_db is not None:
        return _local_db
    with _local_lock:
        if _local_db is None:
            db_path = os.environ.get('OMI_LOCAL_DB_PATH', '/tmp/omi.db')
            _local_db = sqlite3.connect(db_path, check_same_thread=False)
            _local_db.row_factory = sqlite3.Row
            _local_db.execute('PRAGMA journal_mode=WAL')
    return _local_db


def _exec_sql(sql: str, params: tuple = ()):
    conn = _local_db_conn()
    return conn.execute(sql, params)


class LocalDB:
    """Small Firestore-like document store backed by SQLite.

    It intentionally implements only the subset used by the local single-user
    fork, but keeps Firestore's collection/document/query shape so existing
    database modules can run without Firebase credentials.
    """

    def __init__(self, path: str = '', *, collection_group: str | None = None):
        self._path = path.strip('/')
        self._collection_group = collection_group
        self._conn = _local_db_conn()
        self._conn.execute('''
            CREATE TABLE IF NOT EXISTS local_documents (
                path TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')
        self._conn.commit()
        self._filters = []
        self._orders = []
        self._limit = None
        self._offset = 0

    def document_id_from_seed(self, seed: str) -> str:
        return document_id_from_seed(seed)

    def collection(self, name: str):
        return LocalDB(_join_path(self._path, name))

    def collection_group(self, name: str):
        return LocalDB(collection_group=name)

    def document(self, document_id: str | None = None):
        return LocalDocumentReference(_join_path(self._path, document_id or str(uuid.uuid4())))

    def add(self, data, document_id: str | None = None):
        ref = self.document(document_id)
        ref.set(data)
        return None, ref

    def get_all(self, doc_refs, field_paths=None):
        return [ref.get(field_paths=field_paths) for ref in doc_refs]

    def batch(self):
        return LocalBatch()

    def transaction(self):
        return LocalTransaction()

    def get(self, document_id: str | None = None):
        if document_id is not None:
            return self.document(document_id).get().to_dict()
        return list(self.stream())

    def set(self, document_id: str, data):
        self.document(document_id).set(data)

    def delete(self, document_id: str):
        self.document(document_id).delete()

    def where(self, field: str | None = None, op: str | None = None, value=None, *, filter=None):
        query = self._clone()
        if filter is not None:
            query._filters.extend(_flatten_filters(filter))
        elif field is not None:
            query._filters.append((field, op or '==', value))
        return query

    def order_by(self, field: str, direction=None):
        query = self._clone()
        query._orders.append((field, _is_desc(direction)))
        return query

    def limit(self, value: int):
        query = self._clone()
        query._limit = value
        return query

    def offset(self, value: int):
        query = self._clone()
        query._offset = value
        return query

    def count(self):
        return LocalCountQuery(self)

    def list_documents(self):
        return [doc.reference for doc in self._matching_docs()]

    def stream(self):
        docs = self._matching_docs()
        for doc in docs:
            yield doc

    def _clone(self):
        clone = LocalDB(self._path, collection_group=self._collection_group)
        clone._filters = list(self._filters)
        clone._orders = list(self._orders)
        clone._limit = self._limit
        clone._offset = self._offset
        return clone

    def _matching_docs(self):
        cursor = self._conn.execute('SELECT path, data FROM local_documents')
        docs = []
        for row in cursor:
            path = row['path']
            if self._collection_group:
                if not _is_collection_group_doc(path, self._collection_group):
                    continue
            elif not _is_direct_collection_doc(path, self._path):
                continue
            data = json.loads(row['data'])
            doc = LocalDocumentSnapshot(path, data, exists=True)
            if all(_matches_filter(doc, f) for f in self._filters):
                docs.append(doc)
        for field, desc in reversed(self._orders):
            docs.sort(key=lambda doc: _sort_key(_field_value(doc.to_dict() or {}, field)), reverse=desc)
        if self._offset:
            docs = docs[self._offset :]
        if self._limit is not None:
            docs = docs[: self._limit]
        return docs


class LocalDocumentReference:
    def __init__(self, path: str):
        self.path = path.strip('/')
        self.id = self.path.split('/')[-1] if self.path else ''
        self._conn = _local_db_conn()
        self._conn.execute('''
            CREATE TABLE IF NOT EXISTS local_documents (
                path TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')
        self._conn.commit()

    def collection(self, name: str):
        return LocalDB(_join_path(self.path, name))

    def get(self, field_paths=None, transaction=None):
        cursor = self._conn.execute('SELECT data FROM local_documents WHERE path = ?', (self.path,))
        row = cursor.fetchone()
        if row is None:
            return LocalDocumentSnapshot(self.path, None, exists=False)
        data = json.loads(row['data'])
        if field_paths:
            data = {field: _field_value(data, field) for field in field_paths if _field_value(data, field) is not None}
        return LocalDocumentSnapshot(self.path, data, exists=True)

    def set(self, data, merge: bool = False):
        current = self.get().to_dict() if merge else None
        stored = _merge_dicts(current or {}, data or {}) if merge else (data or {})
        self._write(stored)

    def update(self, updates):
        current = self.get().to_dict() or {}
        for key, value in (updates or {}).items():
            _apply_update(current, key, value)
        self._write(current)

    def delete(self):
        self._conn.execute('DELETE FROM local_documents WHERE path = ?', (self.path,))
        self._conn.commit()

    def _write(self, data):
        self._conn.execute(
            'INSERT OR REPLACE INTO local_documents(path, data) VALUES (?, ?)',
            (self.path, json.dumps(_to_jsonable(data), default=str)),
        )
        self._conn.commit()


class LocalDocumentSnapshot:
    def __init__(self, path: str, data, *, exists: bool):
        self.reference = LocalDocumentReference(path)
        self.id = self.reference.id
        self.exists = exists
        self._data = deepcopy(data) if data is not None else None

    def to_dict(self):
        return deepcopy(self._data) if self._data is not None else None

    def get(self, field_path: str, default=None):
        if self._data is None:
            return default
        value = _field_value(self._data, field_path)
        return default if value is None else value


class LocalCountQuery:
    def __init__(self, query: LocalDB):
        self._query = query

    def get(self):
        class _Count:
            def __init__(self, value):
                self.value = value

        return [[_Count(len(list(self._query.stream())))]]


class LocalBatch:
    def __init__(self):
        self._ops = []

    def set(self, ref, data, merge: bool = False):
        self._ops.append(('set', ref, data, merge))

    def update(self, ref, data):
        self._ops.append(('update', ref, data, False))

    def delete(self, ref):
        self._ops.append(('delete', ref, None, False))

    def commit(self):
        for op, ref, data, merge in self._ops:
            if op == 'set':
                ref.set(data, merge=merge)
            elif op == 'update':
                ref.update(data)
            elif op == 'delete':
                ref.delete()
        self._ops = []


class LocalTransaction:
    def get(self, ref):
        return ref.get()

    def update(self, ref, data):
        ref.update(data)

    def set(self, ref, data, merge: bool = False):
        ref.set(data, merge=merge)

    def delete(self, ref):
        ref.delete()


def _join_path(*parts: str | None) -> str:
    return '/'.join(str(part).strip('/') for part in parts if part)


def _is_direct_collection_doc(path: str, collection_path: str) -> bool:
    if collection_path:
        prefix = f'{collection_path}/'
        if not path.startswith(prefix):
            return False
        remainder = path[len(prefix) :]
    else:
        remainder = path
    return remainder != '' and '/' not in remainder


def _is_collection_group_doc(path: str, collection_name: str) -> bool:
    parts = path.split('/')
    return len(parts) >= 2 and len(parts) % 2 == 0 and parts[-2] == collection_name


def _flatten_filters(filter_obj):
    if hasattr(filter_obj, 'filters'):
        filters = []
        for child in filter_obj.filters:
            filters.extend(_flatten_filters(child))
        return filters
    return [(filter_obj.field_path, filter_obj.op_string, filter_obj.value)]


def _matches_filter(doc: LocalDocumentSnapshot, filter_tuple) -> bool:
    field, op, expected = filter_tuple
    actual = doc.id if field == '__name__' else _field_value(doc.to_dict() or {}, field)
    if op == '==':
        return actual == expected
    if op == '!=':
        return actual != expected
    if op == 'in':
        return actual in (expected or [])
    if op == 'not-in':
        return actual not in (expected or [])
    if op == 'array_contains':
        return isinstance(actual, list) and expected in actual
    if op == '>=':
        return actual is not None and actual >= expected
    if op == '>':
        return actual is not None and actual > expected
    if op == '<=':
        return actual is not None and actual <= expected
    if op == '<':
        return actual is not None and actual < expected
    return False


def _field_value(data: dict, field_path: str):
    current = data
    for part in field_path.split('.'):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_field(data: dict, field_path: str, value):
    current = data
    parts = field_path.split('.')
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _delete_field(data: dict, field_path: str):
    current = data
    parts = field_path.split('.')
    for part in parts[:-1]:
        current = current.get(part)
        if not isinstance(current, dict):
            return
    current.pop(parts[-1], None)


def _apply_update(data: dict, field_path: str, value):
    class_name = value.__class__.__name__
    if class_name == 'Sentinel' and getattr(value, 'description', '').lower().find('delete') >= 0:
        _delete_field(data, field_path)
        return
    if class_name == 'ArrayUnion':
        current = _field_value(data, field_path) or []
        for item in value.values:
            if item not in current:
                current.append(item)
        _set_field(data, field_path, current)
        return
    if class_name == 'ArrayRemove':
        current = _field_value(data, field_path) or []
        _set_field(data, field_path, [item for item in current if item not in value.values])
        return
    if class_name == 'Increment':
        current = _field_value(data, field_path) or 0
        _set_field(data, field_path, current + value.value)
        return
    _set_field(data, field_path, value)


def _merge_dicts(base: dict, updates: dict):
    merged = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge_dicts(merged[key], value)
        else:
            merged[key] = value
    return merged


def _to_jsonable(value):
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return value


def _sort_key(value):
    return (value is None, str(value))


def _is_desc(direction) -> bool:
    return 'DESC' in str(direction or '').upper()


# ---------------------------------------------------------------------------
# Module-level db — set at import time: a real Firestore client if
# credentials are available, otherwise a LocalDB('users').  This way
# callers that do `from ._client import db, document_id_from_seed` get
# a usable object either way.
# ---------------------------------------------------------------------------
db = _get_firestore_client()
if db is None:
    db = LocalDB()


def get_users_uid():
    if hasattr(db, 'stream'):
        users_ref = db.collection('users')
        return [str(doc.id) for doc in users_ref.stream()]
    return []


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)


# Factory that returns either the real Firebase client or a LocalDB.
def get_db():
    """Return a Firestore collection ('users') — or LocalDB fallback."""
    if os.environ.get('SERVICE_ACCOUNT_JSON'):
        return db
    return LocalDB()
