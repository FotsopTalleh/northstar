import logging
import firebase_admin
from firebase_admin import credentials, firestore
from app.config import Config

logger = logging.getLogger(__name__)
_db = None
_init_error = None


def init_firebase():
    global _db, _init_error
    try:
        if not firebase_admin._apps:
            if Config.FIREBASE_CREDENTIALS_JSON:
                import json
                cred_dict = json.loads(Config.FIREBASE_CREDENTIALS_JSON)
                cred = credentials.Certificate(cred_dict)
            else:
                cred = credentials.Certificate(Config.FIREBASE_CREDENTIALS_PATH)
            firebase_admin.initialize_app(cred)
        _db = firestore.client()
        logger.info("[Firebase] Connected to Firestore successfully.")
    except Exception as e:
        _init_error = str(e)
        logger.warning(f"[Firebase] Could not connect to Firestore: {e}")
        logger.warning("[Firebase] Add your firebase_credentials.json and restart the server.")


def get_db():
    global _db, _init_error
    if _db is None:
        if _init_error:
            from flask import abort
            abort(503, description=f"Firestore unavailable: {_init_error}. "
                  "Please add firebase_credentials.json and restart.")
        init_firebase()
    return _db
