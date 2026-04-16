import os
from dotenv import load_dotenv
load_dotenv('.env')

from app.firebase import get_db

db = get_db()
try:
    plans = (
        db.collection("daily_plans")
        .where("user_id", "==", "test_user_123")
        .where("date", "==", "2024-01-01")
        .where("locked", "==", True)
        .limit(1)
        .get()
    )
    print("Multi-where Success:", len(plans))
except Exception as e:
    print("Error:", str(e))
