# NOTE: Firebase removed for local dev — use admin key auth instead.
from database._client import db
from database.redis_db import cache_user_name
import logging

logger = logging.getLogger(__name__)


def get_user_from_uid(uid: str):
    """Local dev stub: return user info from local DB or None.
    
    In production, this queries Firebase Auth. For local dev,
    the admin key auth flow (ADMIN_KEY<uid>) provides identity
    without Firebase."""
    if not uid:
        return None
    try:
        # Try to get user from local users table
        user = db.collection('users').document(uid).get()
        if user.exists:
            data = user.to_dict()
            return {
                'uid': uid,
                'email': data.get('email'),
                'email_verified': True,
                'phone_number': data.get('phone_number'),
                'display_name': data.get('name', ''),
                'photo_url': data.get('photo_url'),
                'disabled': data.get('disabled', False),
            }
    except Exception as e:
        logger.error(f'get_user_from_uid failed: {e}')
    return None


def _get_firestore_user_name(uid: str):
    """Fallback: get user name from Firestore user profile."""
    try:
        user_doc = db.collection('users').document(uid).get()
        if user_doc.exists:
            name = user_doc.to_dict().get('name')
            if name and isinstance(name, str):
                return name.split(' ')[0]
    except Exception as e:
        logger.error(f"Firestore user name lookup failed: {e}")
    return None


def get_user_name(uid: str, use_default: bool = True):
    default_name = 'The User' if use_default else None
    user = get_user_from_uid(uid)
    if not user:
        # Fallback to Firestore profile
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            cache_user_name(uid, firestore_name, ttl=60 * 60)
            return firestore_name
        return default_name

    display_name = user.get('display_name')
    if not display_name:
        # Fallback to Firestore profile
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            cache_user_name(uid, firestore_name, ttl=60 * 60)
            return firestore_name
        return default_name

    display_name = display_name.split(' ')[0]
    if display_name == 'AnonymousUser':
        firestore_name = _get_firestore_user_name(uid)
        if firestore_name:
            display_name = firestore_name
        else:
            display_name = default_name

    cache_user_name(uid, display_name, ttl=60 * 60)
    return display_name
