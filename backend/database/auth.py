from database._client import db
from database.redis_db import cache_user_name
import logging

logger = logging.getLogger(__name__)


def get_user_from_uid(uid: str):
    """Return user info from the local DB or None.
    
    For the local fork, uid lookup is done against the SQLite
    fallback in _client.py.
    """
    if not uid:
        return None
    try:
        # The LocalDB fallback doesn't have .document(), so we
        # query the users table directly.
        user = db.get(uid)
        if user:
            return {
                'uid': uid,
                'email': user.get('email'),
                'email_verified': True,
                'phone_number': user.get('phone_number'),
                'display_name': user.get('name', ''),
                'photo_url': user.get('photo_url'),
                'disabled': user.get('disabled', False),
            }
    except Exception as e:
        logger.error(f'get_user_from_uid failed: {e}')
    return None


def _get_user_name_from_db(uid: str):
    """Fallback: get user name from the local DB."""
    try:
        user = db.get(uid)
        if user and 'name' in user:
            name = user['name']
            if isinstance(name, str):
                return name.split(' ')[0]
    except Exception as e:
        logger.error(f"User name lookup failed: {e}")
    return None


def get_user_name(uid: str, use_default: bool = True):
    default_name = 'The User' if use_default else None
    user = get_user_from_uid(uid)
    if not user:
        # Fallback to local DB profile
        db_name = _get_user_name_from_db(uid)
        if db_name:
            cache_user_name(uid, db_name, ttl=60 * 60)
            return db_name
        return default_name

    display_name = user.get('display_name')
    if not display_name:
        # Fallback to local DB profile
        db_name = _get_user_name_from_db(uid)
        if db_name:
            cache_user_name(uid, db_name, ttl=60 * 60)
            return db_name
        return default_name

    display_name = display_name.split(' ')[0]
    if display_name == 'AnonymousUser':
        db_name = _get_user_name_from_db(uid)
        if db_name:
            display_name = db_name
        else:
            display_name = default_name

    cache_user_name(uid, display_name, ttl=60 * 60)
    return display_name
