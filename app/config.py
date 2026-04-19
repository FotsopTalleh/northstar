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
