import hashlib
import json
import os
import sqlite3
import threading
import uuid

from google.cloud import firestore

if os.environ.get('SERVICE_ACCOUNT_JSON'):
    service_account_info = json.loads(os.environ["SERVICE_ACCOUNT_JSON"])
    # create google-credentials.json
    with open('google-credentials.json', 'w') as f:
        json.dump(service_account_info, f)

db = firestore.Client()


def get_users_uid():
    users_ref = db.collection('users')
    return [str(doc.id) for doc in users_ref.stream()]


def document_id_from_seed(seed: str) -> uuid.UUID:
    """Avoid repeating the same data"""
    seed_hash = hashlib.sha256(seed.encode('utf-8')).digest()
    generated_uuid = uuid.UUID(bytes=seed_hash[:16], version=4)
    return str(generated_uuid)


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


# Minimal wrapper — not all callers expect this.
class LocalDB:
    def __init__(self, collection: str):
        self._collection = collection
        self._table = f'{collection}_data'
        self._conn = _local_db_conn()
        self._conn.execute(f'''
            CREATE TABLE IF NOT EXISTS {self._table} (
                document_id TEXT PRIMARY KEY,
                data TEXT NOT NULL
            )
        ''')
        self._conn.commit()

    def document_id_from_seed(self, seed: str) -> str:
        return document_id_from_seed(seed)

    def get(self, document_id: str):
        cursor = self._conn.execute(
            f'SELECT data FROM {self._table} WHERE document_id = ?', (document_id,),
        )
        row = cursor.fetchone()
        if row:
            return json.loads(row['data'])
        return None

    def set(self, document_id: str, data):
        self._conn.execute(
            f'INSERT OR REPLACE INTO {self._table} VALUES (?, ?)',
            (document_id, json.dumps(data)),
        )
        self._conn.commit()

    def delete(self, document_id: str):
        self._conn.execute(
            f'DELETE FROM {self._table} WHERE document_id = ?', (document_id,),
        )
        self._conn.commit()

    def collection(self, name: str):
        """Return a new LocalDB for a different collection."""
        return LocalDB(name)

    def stream(self):
        """Iterate all documents."""
        cursor = self._conn.execute(f'SELECT document_id, data FROM {self._table}')
        for row in cursor:
            yield _FakeDoc(row['document_id'], json.loads(row['data']))

    def where(self, field: str, op: str, value):
        """Filter — returns a list of dicts. Not all callers use this."""
        cursor = self._conn.execute(
            f'SELECT document_id, data FROM {self._table} WHERE data->? {op} ?',
            (field, value),
        )
        results = []
        for row in cursor:
            d = json.loads(row['data'])
            results.append(_FakeDoc(row['document_id'], d))
        return results


class _FakeDoc:
    def __init__(self, id: str, data):
        self.id = id
        self.data = data
        self.get = lambda k, default=None: json.loads(self.data).get(k, default)


# Factory that returns either the real Firebase client or a LocalDB.
def get_db():
    """Return a Firestore collection ('users') — or LocalDB fallback."""
    if os.environ.get('SERVICE_ACCOUNT_JSON'):
        return db
    return LocalDB('users')


# Alias for callers that do `from database._client import db` directly.
# This is the main entry point — all other modules import `db` from here.
# For the local fork, `db` is replaced with a factory function.
def __getattr__(name):
    if name == 'db':
        return get_db()
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
