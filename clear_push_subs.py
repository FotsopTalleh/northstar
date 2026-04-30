"""
clear_push_subs.py — Clears all push_subscriptions for a user so they
can re-register fresh with the current VAPID key.
Run: python clear_push_subs.py afoutalleh@gmail.com
"""
import os, sys
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(".env")

from app.firebase import get_db, init_firebase
init_firebase()

def clear_subs(email):
    db = get_db()
    users = db.collection("users").where("email", "==", email).limit(1).get()
    if not users:
        print("User not found.")
        return

    doc = users[0]
    user_data = doc.to_dict()
    old_count = len(user_data.get("push_subscriptions", []))

    doc.reference.update({"push_subscriptions": []})
    print(f"Cleared {old_count} expired/mismatched subscriptions for {user_data.get('username')} ({email}).")
    print("The user must now visit the Profile page (on Railway) to re-register a fresh subscription.")

if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "afoutalleh@gmail.com"
    clear_subs(email)
