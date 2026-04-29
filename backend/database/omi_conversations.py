"""
TimescaleDB-backed conversations module for omi-fork.
Replaces the Firestore backend.
"""

import json
import uuid
import zlib
import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

# Connection string from env var or default
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/omi"

# Try to read from env var
import os
if os.environ.get("POSTGRES_URI"):
    DATABASE_URL = os.environ["POSTGRES_URI"]


def _get_conn():
    """Get a database connection."""
    return psycopg2.connect(DATABASE_URL)


def _get_uid_from_uuid(uuid_str: str) -> str:
    """Extract the user UID from the user UUID (format: user-{uid})."""
    return uuid_str.split("-")[-1]


def _ensure_timezone_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def _serialize_row(row):
    """Convert a psycopg2 row tuple to a dict."""
    if row is None:
        return None
    return dict(zip([c[0] for c in row[0].cursor.description], row[1]))


def _serialize_rows(rows):
    """Convert a list of psycopg2 rows to a list of dicts."""
    if not rows:
        return []
    cols = [c[0] for c in rows[0][0].cursor.description]
    return [dict(zip(cols, row[1])) for row in rows]


def _serialize_row_single(row):
    """Convert a single psycopg2 row to a dict (for non-cursor wrappers)."""
    if row is None:
        return None
    return dict(zip([c[0] for c in row.cursor.description], row))


def _serialize_rows_single(rows):
    """Convert a list of rows to dicts (for non-cursor wrappers)."""
    if not rows:
        return []
    cols = [c[0] for c in rows[0].cursor.description]
    return [dict(zip(cols, row)) for row in rows]


# ---- Helpers (same as original) ----

def _decrypt_conversation_data(conversation_data, uid):
    data = copy.deepcopy(conversation_data)
    if "transcript_segments" not in data:
        return data
    if isinstance(data["transcript_segments"], str):
        try:
            from utils import encryption
            decrypted_payload = encryption.decrypt(data["transcript_segments"], uid)
            if data.get("transcript_segments_compressed"):
                compressed_bytes = bytes.fromhex(decrypted_payload)
                decompressed_json = zlib.decompress(compressed_bytes).decode("utf-8")
                data["transcript_segments"] = json.loads(decompressed_json)
            else:
                data["transcript_segments"] = json.loads(decrypted_payload)
        except Exception as e:
            logger.error(f"{e} {uid}")
            data["transcript_segments"] = []
    elif isinstance(data["transcript_segments"], bytes):
        try:
            compressed_bytes = data["transcript_segments"]
            if data.get("transcript_segments_compressed"):
                decompressed_json = zlib.decompress(compressed_bytes).decode("utf-8")
                data["transcript_segments"] = json.loads(decompressed_json)
        except Exception as e:
            logger.error(f"{e}")
            pass
    return data


def _prepare_conversation_for_write(data, uid, level="standard"):
    data = copy.deepcopy(data)
    if "transcript_segments" in data and isinstance(data["transcript_segments"], list):
        segments_json = json.dumps(data["transcript_segments"])
        compressed_segments_bytes = zlib.compress(segments_json.encode("utf-8"))
        data["transcript_segments_compressed"] = True
        if level == "enhanced":
            from utils import encryption
            encrypted_segments = encryption.encrypt(compressed_segments_bytes.hex(), uid)
            data["transcript_segments"] = encrypted_segments
        else:
            data["transcript_segments"] = compressed_segments_bytes
    return data


def _prepare_conversation_for_read(conversation_data, uid):
    if not conversation_data:
        return None
    data = copy.deepcopy(conversation_data)
    level = data.get("data_protection_level")
    if level == "enhanced":
        return _decrypt_conversation_data(data, uid)
    if data.get("transcript_segments_compressed"):
        if "transcript_segments" in data and isinstance(data["transcript_segments"], bytes):
            try:
                decompressed_json = zlib.decompress(data["transcript_segments"]).decode("utf-8")
                data["transcript_segments"] = json.loads(decompressed_json)
            except Exception:
                pass
    return data


def _prepare_photo_for_write(data, uid, level):
    data = copy.deepcopy(data)
    data["data_protection_level"] = level
    if level == "enhanced" and "base64" in data and isinstance(data["base64"], str):
        from utils import encryption
        data["base64"] = encryption.encrypt(data["base64"], uid)
    return data


def _prepare_photo_for_read(photo_data, uid):
    if not photo_data:
        return None
    data = copy.deepcopy(photo_data)
    level = data.get("data_protection_level")
    if level == "enhanced" and "base64" in data and isinstance(data["base64"], str):
        try:
            data["base64"] = encryption.decrypt(data["base64"], uid)
        except Exception:
            pass
    return data


# ---- CRUD ----

def upsert_conversation(uid, conversation_data):
    if "audio_base64_url" in conversation_data:
        del conversation_data["audio_base64_url"]
    if "photos" in conversation_data:
        del conversation_data["photos"]
    conv_id = conversation_data["id"]
    prepared = _prepare_conversation_for_write(conversation_data, uid, "standard")
    prepared["user_id"] = uid
    prepared["created_at"] = prepared.get("created_at") or datetime.now(timezone.utc)
    prepared["updated_at"] = datetime.now(timezone.utc)
    prepared["status"] = prepared.get("status", "completed")
    prepared["discarded"] = prepared.get("discarded", False)

    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """INSERT INTO conversations (id, user_id, created_at, updated_at, status, discarded,
                   transcript_segments, structured, data_protection_level, starred, folder_id,
                   language, is_locked, display_name)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (id, user_id) DO UPDATE SET
                   created_at=EXCLUDED.created_at, updated_at=EXCLUDED.updated_at,
                   status=EXCLUDED.status, discarded=EXCLUDED.discarded,
                   transcript_segments=EXCLUDED.transcript_segments, structured=EXCLUDED.structured,
                   data_protection_level=EXCLUDED.data_protection_level, starred=EXCLUDED.starred,
                   folder_id=EXCLUDED.folder_id, language=EXCLUDED.language,
                   is_locked=EXCLUDED.is_locked, display_name=EXCLUDED.display_name""",
                (conv_id, uid, prepared["created_at"], prepared["updated_at"],
                 prepared["status"], prepared.get("discarded", False),
                 prepared["transcript_segments"], prepared.get("structured"),
                 prepared.get("data_protection_level", "standard"),
                 prepared.get("starred", False), prepared.get("folder_id"),
                 prepared.get("language"), prepared.get("is_locked", False),
                 prepared.get("display_name"))
            )
            conn.commit()


def _get_conversation_by_id(uid, conversation_id):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE id=%s AND user_id=%s",
                (conversation_id, uid)
            )
            row = cur.fetchone()
    if not row:
        return None
    data = dict(zip([c[0] for c in cur.description], row))
    data = _prepare_conversation_for_read(data, uid)
    return data


def get_conversation(uid, conversation_id):
    return _get_conversation_by_id(uid, conversation_id)


def get_conversations(
    uid, limit=100, offset=0,
    include_discarded=False, statuses=[],
    start_date=None, end_date=None,
    categories=None, folder_id=None, starred=None
):
    conditions = ["user_id = %s"]
    params = [uid]
    if not include_discarded:
        conditions.append("discarded = FALSE")
    if statuses:
        placeholders = ",".join(["%s"] * len(statuses))
        conditions.append(f"status IN ({placeholders})")
        params.extend(statuses)
    if folder_id:
        conditions.append("folder_id = %s")
        params.append(folder_id)
    if starred is not None:
        conditions.append("starred = %s")
        params.append(starred)
    if start_date:
        conditions.append("created_at >= %s")
        params.append(start_date)
    if end_date:
        conditions.append("created_at <= %s")
        params.append(end_date)
    sql = f"SELECT * FROM conversations WHERE {' AND '.join(conditions)} ORDER BY created_at DESC LIMIT %s OFFSET %s"
    params.extend([limit, offset])
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    conversations = []
    for row in rows:
        data = dict(zip([c[0] for c in cur.description], row))
        data = _prepare_conversation_for_read(data, uid)
        conversations.append(data)
    return conversations


def get_conversations_without_photos(uid, limit=100, offset=0,
    include_discarded=False, statuses=[],
    start_date=None, end_date=None,
    categories=None, folder_id=None, starred=None
):
    return get_conversations(uid, limit, offset, include_discarded,
                             statuses, start_date, end_date,
                             categories, folder_id, starred)


def get_conversations_count(uid, include_discarded=False, statuses=[]):
    conditions = ["user_id = %s"]
    params = [uid]
    if not include_discarded:
        conditions.append("discarded = FALSE")
    if statuses:
        placeholders = ",".join(["%s"] * len(statuses))
        conditions.append(f"status IN ({placeholders})")
        params.extend(statuses)
    sql = f"SELECT COUNT(*) FROM conversations WHERE {' AND '.join(conditions)}"
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return int(cur.fetchone()[0])


def iter_all_conversations(uid, batch_size=400, include_discarded=True):
    conditions = ["user_id = %s"]
    params = [uid]
    if not include_discarded:
        conditions.append("discarded = FALSE")
    offset = 0
    while True:
        page_params = params + [batch_size, offset]
        with _get_conn() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT * FROM conversations WHERE {' AND '.join(conditions)} "
                    f"ORDER BY created_at DESC LIMIT %s OFFSET %s",
                    page_params
                )
                rows = cur.fetchall()
                if not rows:
                    break
                cols = [c[0] for c in cur.description]
                for row in rows:
                    data = dict(zip(cols, row))
                    data = _prepare_conversation_for_read(data, uid) or data
                    yield data
        if len(rows) < batch_size:
            break
        offset += batch_size


def update_conversation(uid, conversation_id, update_data):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    doc_level = doc.get("data_protection_level", "standard")
    prepared = _prepare_conversation_for_write(update_data, uid, doc_level)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, status=%s, structured=%s, "
                "transcript_segments=%s WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 prepared.get("status", doc.get("status")),
                 prepared.get("structured"),
                 prepared.get("transcript_segments"),
                 conversation_id, uid)
            )
            conn.commit()


def update_conversation_title(uid, conversation_id, title):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, display_name=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), title, conversation_id, uid)
            )
            conn.commit()


def update_conversation_status(uid, conversation_id, status):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, status=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), str(status), conversation_id, uid)
            )
            conn.commit()


def set_conversation_as_discarded(uid, conversation_id):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, discarded=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), True, conversation_id, uid)
            )
            conn.commit()


def update_conversation_segments(uid, conversation_id, segments):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    doc_level = doc.get("data_protection_level", "standard")
    prepared = _prepare_conversation_for_write({"transcript_segments": segments}, uid, doc_level)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, transcript_segments=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 prepared["transcript_segments"],
                 conversation_id, uid)
            )
            conn.commit()


def update_conversation_events(uid, conversation_id, events):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    structured = doc.get("structured", {}) or {}
    structured["events"] = events
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, structured=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 json.dumps(structured),
                 conversation_id, uid)
            )
            conn.commit()


def update_conversation_action_items(uid, conversation_id, action_items):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    structured = doc.get("structured", {}) or {}
    structured["action_items"] = action_items
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, structured=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 json.dumps(structured),
                 conversation_id, uid)
            )
            conn.commit()


def update_conversation_segment_text(uid, conversation_id, segment_id, text):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return "not_found"
    if doc.get("is_locked", False):
        return "locked"
    segments = doc.get("transcript_segments", [])
    found = False
    for segment in segments:
        if isinstance(segment, dict) and segment.get("id") == segment_id:
            segment["text"] = text
            found = True
            break
    if not found:
        return "segment_not_found"
    doc_level = doc.get("data_protection_level", "standard")
    prepared = _prepare_conversation_for_write({"transcript_segments": segments}, uid, doc_level)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, transcript_segments=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), prepared["transcript_segments"],
                 conversation_id, uid)
            )
            conn.commit()
    return "ok"


def get_in_progress_conversation(uid):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE user_id=%s AND status='processing' "
                "ORDER BY created_at DESC LIMIT 1",
                (uid,)
            )
            row = cur.fetchone()
    if not row:
        return None
    data = dict(zip([c[0] for c in cur.description], row))
    data = _prepare_conversation_for_read(data, uid)
    return data


def get_processing_conversations(uid):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE user_id=%s AND status='processing' "
                "ORDER BY created_at DESC",
                (uid,)
            )
            rows = cur.fetchall()
    return [dict(zip([c[0] for c in cur.description], row))
            for row in rows]


def get_last_completed_conversation(uid):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE user_id=%s AND status='completed' "
                "ORDER BY created_at DESC LIMIT 1",
                (uid,)
            )
            row = cur.fetchone()
    if not row:
        return None
    data = dict(zip([c[0] for c in cur.description], row))
    data = _prepare_conversation_for_read(data, uid)
    return data


def delete_conversation(uid, conversation_id):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM conversations WHERE id=%s AND user_id=%s",
                (conversation_id, uid)
            )
            conn.commit()


def get_action_items(uid, conversation_id):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return []
    structured = doc.get("structured", {}) or {}
    return structured.get("action_items", [])


def set_conversation_visibility(uid, conversation_id, visibility):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, display_name=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), visibility, conversation_id, uid)
            )
            conn.commit()


def set_conversation_starred(uid, conversation_id, starred):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, starred=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), starred, conversation_id, uid)
            )
            conn.commit()


def unlock_all_conversations(uid):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET is_locked=%s WHERE user_id=%s",
                (False, uid)
            )
            conn.commit()


def set_postprocessing_status(uid, conversation_id, model, status):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    structured = doc.get("structured", {}) or {}
    model_key = f"{model}_status"
    structured[model_key] = status
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, structured=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 json.dumps(structured),
                 conversation_id, uid)
            )
            conn.commit()


def store_model_segments_result(uid, conversation_id, model, segments):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    structured = doc.get("structured", {}) or {}
    model_key = f"{model}_segments"
    structured[model_key] = segments
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, structured=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 json.dumps(structured),
                 conversation_id, uid)
            )
            conn.commit()


def store_model_emotion_predictions_result(uid, conversation_id, model, predictions):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    structured = doc.get("structured", {}) or {}
    model_key = f"{model}_emotion_predictions"
    structured[model_key] = predictions
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, structured=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 json.dumps(structured),
                 conversation_id, uid)
            )
            conn.commit()


def get_conversation_transcripts_by_model(uid, conversation_id):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return {}
    structured = doc.get("structured", {}) or {}
    result = {}
    for model in ["whisper", "deepgram", "whisper_16khz", "whisper_24khz"]:
        segments = structured.get(f"{model}_segments")
        if segments:
            result[model] = segments
    return result


def store_conversation_photos(uid, conversation_id, photos):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return
    level = doc.get("data_protection_level", "standard")
    prepared_photos = [_prepare_photo_for_write(p, uid, level) for p in photos]
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, photos=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc),
                 json.dumps(prepared_photos),
                 conversation_id, uid)
            )
            conn.commit()


def get_conversation_photos(uid, conversation_id):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return []
    photos = doc.get("photos", [])
    photos = [_prepare_photo_for_read(p, uid) for p in photos]
    return photos


def get_closest_conversation_to_timestamps(uid, timestamps):
    if not timestamps:
        return None
    min_ts = min(timestamps)
    max_ts = max(timestamps)
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE user_id=%s "
                "AND created_at BETWEEN %s AND %s "
                "ORDER BY ABS(EXTRACT(EPOCH FROM created_at) - %s) ASC LIMIT 1",
                (uid, min_ts, max_ts, min_ts)
            )
            row = cur.fetchone()
    if not row:
        return None
    data = dict(zip([c[0] for c in cur.description], row))
    data = _prepare_conversation_for_read(data, uid)
    return data


def get_conversations_by_id(uid, conversation_ids):
    if not conversation_ids:
        return []
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE user_id=%s AND id=ANY(%s)",
                (uid, conversation_ids)
            )
            rows = cur.fetchall()
    return [dict(zip([c[0] for c in cur.description], row))
            for row in rows]


def get_conversations_to_migrate(uid):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM conversations WHERE user_id=%s "
                "AND (data_protection_level IS NULL OR data_protection_level = 'standard') "
                "LIMIT 100",
                (uid,)
            )
            rows = cur.fetchall()
    return [dict(zip([c[0] for c in cur.description], row)) for row in rows]


def migrate_conversations_level_batch(uid, new_level):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, data_protection_level=%s "
                "WHERE user_id=%s AND data_protection_level IN ('standard', NULL)",
                (datetime.now(timezone.utc), new_level, uid)
            )
            conn.commit()


def update_conversation_finished_at(uid, conversation_id, finished_at):
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, finished_at=%s "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), finished_at, conversation_id, uid)
            )
            conn.commit()


def create_audio_files_from_chunks(uid, conversation_id):
    """Stub: no audio files for now."""
    return []


def delete_conversation_photos(uid, conversation_id):
    doc = _get_conversation_by_id(uid, conversation_id)
    if not doc:
        return 0
    count = 0
    with _get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE conversations SET updated_at=%s, photos=NULL "
                "WHERE id=%s AND user_id=%s",
                (datetime.now(timezone.utc), conversation_id, uid)
            )
            conn.commit()
    return count


def get_user_data_protection_level(uid):
    return "standard"


def get_user_transcription_preferences(uid):
    return {"single_language_mode": False, "vocabulary": []}
