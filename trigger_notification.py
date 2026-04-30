"""
trigger_notification.py
=====================================================================
Manually fire any real day-to-day scheduler job to verify that
OS push notifications actually reach your device.

Usage:
  python trigger_notification.py morning          # 08:00 job
  python trigger_notification.py evening          # 20:00 job
  python trigger_notification.py midnight         # 00:00 job (careful!)
  python trigger_notification.py test <email>     # fastest: direct push

Runs inside a real Flask app context - identical to production.
"""
import sys
import os

# ASCII-safe output for Windows terminals
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(".env")

# Boot Flask app
from app import create_app
app = create_app()


def _banner(title):
    print("\n" + "=" * 55)
    print("  " + title)
    print("=" * 55)


def run_morning():
    _banner("MORNING reminder job (08:00 UTC logic)")
    from app.scheduler import _run_morning_reminder_job
    with app.app_context():
        _run_morning_reminder_job()
    print("\n[OK] Done - check your device for a push notification.")


def run_evening():
    _banner("EVENING reminder job (20:00 UTC logic)")
    from app.scheduler import _run_evening_reminder_job
    with app.app_context():
        _run_evening_reminder_job()
    print("\n[OK] Done - check your device for a push notification.")


def run_midnight():
    _banner("MIDNIGHT finalization job (00:00 UTC logic)")
    print("  [!!] This finalizes XP for ALL users - run with care!")
    confirm = input("  Type YES to continue: ").strip()
    if confirm != "YES":
        print("  Aborted.")
        return
    from app.scheduler import _run_midnight_job
    with app.app_context():
        _run_midnight_job()
    print("\n[OK] Done.")


def run_direct_test(email):
    """
    Bypass the scheduler entirely.
    Sends a push directly to the given user's push subscriptions.
    This is the fastest way to confirm VAPID delivery works.
    """
    _banner(f"Direct push test -> {email}")
    with app.app_context():
        from app.firebase import get_db
        from app.services.notification_service import create_notification
        import time

        db = get_db()
        users = db.collection("users").where("email", "==", email).limit(1).get()
        if not users:
            print(f"  [XX] No user found with email: {email}")
            return

        user_doc  = users[0]
        user_data = user_doc.to_dict()
        username  = user_data.get("username", "?")
        subs      = user_data.get("push_subscriptions", [])
        notif_on  = user_data.get("notifications_enabled", True)

        print(f"  User          : {username}")
        print(f"  Notifications : {'ENABLED' if notif_on else 'DISABLED [!!]'}")
        print(f"  Push subs     : {len(subs)}")

        if not notif_on:
            print("\n  [!!] Notifications are OFF for this user.")
            print("       Enable them on the Profile page first, then re-run.")
            return

        if not subs:
            print("\n  [!!] No push subscriptions found.")
            print("       Fix:")
            print("       1. Open the app in your browser / installed PWA")
            print("       2. Go to Profile -> Notifications")
            print("       3. Toggle ON and allow the browser permission prompt")
            print("       4. Run this script again")
            return

        print(f"\n  Sending notification to {len(subs)} subscription(s)...")
        notif_id = create_notification(
            user_id    = user_doc.id,
            notif_type = "tasks_pending_reminder",
            message    = "[TEST] Real daily reminder: you have pending tasks!",
        )
        print(f"  Notification ID : {notif_id}")
        print("  Waiting 12 s for the background push thread to complete...")
        time.sleep(12)
        print("\n[OK] Done - check your device/browser for the OS popup.")


if __name__ == "__main__":
    cmd = sys.argv[1].lower() if len(sys.argv) > 1 else ""

    if cmd == "morning":
        run_morning()
    elif cmd == "evening":
        run_evening()
    elif cmd == "midnight":
        run_midnight()
    elif cmd == "test" and len(sys.argv) > 2:
        run_direct_test(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(1)
