import os
import sys

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv('.env')

from app.firebase import get_db
from app.services.notification_service import create_notification

def send_test_to_email(email, title="Test Alert", message="This is a test notification from the CLI!"):
    db = get_db()
    
    print(f"Searching for user with email: {email}...")
    users = db.collection("users").where("email", "==", email).limit(1).get()
    
    if not users:
        print(f"Error: No user found with email {email}")
        return
    
    user_doc = users[0]
    user_id = user_doc.id
    user_data = user_doc.to_dict()
    username = user_data.get("username", "User")
    
    print(f"Found user: {username} (ID: {user_id})")
    
    # Check if they have notifications enabled
    if not user_data.get("notifications_enabled", True):
        print("Warning: User has notifications disabled in their settings.")
    
    # Check if they have push subscriptions
    subs = user_data.get("push_subscriptions", [])
    if not subs:
        print("Warning: User has no push subscriptions. They will see this in the app bell, but not as an OS popup.")
    else:
        print(f"User has {len(subs)} active push subscription(s). Sending OS popup...")

    # Trigger notification
    notif_id = create_notification(
        user_id=user_id,
        notif_type="reached_top", # Uses trophy icon
        message=message
    )
    
    print(f"Success! Notification created with ID: {notif_id}")
    print("If the user is online or has PWA installed, they should receive it shortly.")

import time

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_push_by_email.py <user_email> [message]")
    else:
        email = sys.argv[1]
        msg = sys.argv[2] if len(sys.argv) > 2 else "This is a test notification from the CLI!"
        send_test_to_email(email, message=msg)
        print("Waiting 15 seconds for background thread to send the push and clean up old subscriptions...")
        time.sleep(15)
