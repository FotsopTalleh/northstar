import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY               = os.environ.get("SECRET_KEY", "changethis_in_production")
    FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "./firebase_credentials.json")
    FIREBASE_CREDENTIALS_JSON = os.environ.get("FIREBASE_CREDENTIALS_JSON")
    JWT_EXPIRY_HOURS         = 72

    # SMTP — for password reset emails
    SMTP_EMAIL    = os.environ.get("SMTP_EMAIL", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    APP_URL       = os.environ.get("APP_URL", "https://web-production-ca0e.up.railway.app")

    # Google OAuth — for Sign in with Google
    GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

    # Web Push (VAPID) — legacy, kept for backward compat
    VAPID_PUBLIC_KEY  = os.environ.get("VAPID_PUBLIC_KEY", "")
    VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
    VAPID_EMAIL       = os.environ.get("VAPID_EMAIL", "")

    # Firebase Web App config (safe to expose publicly to the frontend)
    FIREBASE_API_KEY             = os.environ.get("FIREBASE_API_KEY", "")
    FIREBASE_AUTH_DOMAIN         = os.environ.get("FIREBASE_AUTH_DOMAIN", "")
    FIREBASE_PROJECT_ID          = os.environ.get("FIREBASE_PROJECT_ID", "xpforge-1ccd8")
    FIREBASE_STORAGE_BUCKET      = os.environ.get("FIREBASE_STORAGE_BUCKET", "")
    FIREBASE_MESSAGING_SENDER_ID = os.environ.get("FIREBASE_MESSAGING_SENDER_ID", "")
    FIREBASE_APP_ID              = os.environ.get("FIREBASE_APP_ID", "")
    # VAPID key used by Firebase Messaging (from Firebase Console → Cloud Messaging → Web Push certificates)
    FIREBASE_VAPID_KEY           = os.environ.get("FIREBASE_VAPID_KEY", "")
