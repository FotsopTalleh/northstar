"""
diagnose_push.py — directly sends a webpush and shows any errors.
Run: python diagnose_push.py afoutalleh@gmail.com
"""
import os, sys, json, logging
logging.basicConfig(level=logging.WARNING)

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from dotenv import load_dotenv
load_dotenv(".env")

from app.firebase import get_db, init_firebase
from app.config import Config

init_firebase()

def diagnose(email):
    db = get_db()
    users = db.collection("users").where("email", "==", email).limit(1).get()
    if not users:
        print(" User not found")
        return

    user_data = users[0].to_dict()
    subs = user_data.get("push_subscriptions", [])

    print(f"\n{'='*55}")
    print(f"User       : {user_data.get('username')} ({email})")
    print(f"Notif on?  : {user_data.get('notifications_enabled', True)}")
    print(f"Subscriptions found: {len(subs)}")
    print(f"VAPID public key   : {Config.VAPID_PUBLIC_KEY[:30]}..." if Config.VAPID_PUBLIC_KEY else "VAPID_PUBLIC_KEY  : ⚠️  EMPTY — not set in .env")
    print(f"VAPID private key  : {Config.VAPID_PRIVATE_KEY[:15]}..." if Config.VAPID_PRIVATE_KEY else "VAPID_PRIVATE_KEY : ⚠️  EMPTY — not set in .env")
    print(f"VAPID email        : {Config.VAPID_EMAIL}")
    print(f"{'='*55}\n")

    if not subs:
        print("  No subscriptions — user must visit profile.html and re-enable notifications.")
        return

    from pywebpush import webpush, WebPushException

    payload = json.dumps({"title": "XPForge Test", "body": "Direct push diagnostic test 🔔"})

    for i, sub in enumerate(subs):
        endpoint = sub.get("endpoint", "")
        print(f"[{i+1}/{len(subs)}] Testing: {endpoint[:60]}...")
        try:
            webpush(
                subscription_info={"endpoint": endpoint, "keys": sub.get("keys", {})},
                data=payload,
                vapid_private_key=Config.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{Config.VAPID_EMAIL}"},
            )
            print(f"  SUCCESS -- Sent successfully!\n")
        except WebPushException as ex:
            status = ex.response.status_code if ex.response else "N/A"
            body   = ex.response.text[:200] if ex.response else "(no response body)"
            print(f"  FAIL -- WebPushException HTTP {status}")
            print(f"  Detail: {repr(ex)}")
            if body:
                print(f"  Body  : {body}")
            print()
        except Exception as e:
            print(f"  ERROR: {e}\n")

if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "afoutalleh@gmail.com"
    diagnose(email)
