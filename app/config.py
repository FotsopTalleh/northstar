import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "changethis_in_production")
    FIREBASE_CREDENTIALS_PATH = os.environ.get("FIREBASE_CREDENTIALS_PATH", "./firebase_credentials.json")
    JWT_EXPIRY_HOURS = 72
