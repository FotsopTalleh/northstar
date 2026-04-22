import json
import logging
from pywebpush import webpush, WebPushException
from app.config import Config
from app.firebase import get_db

logger = logging.getLogger(__name__)

def send_web_push(user_id: str, title: str, body: str, icon: str = "/icons/icon-192x192.png", url: str = "/notifications.html"):
    """
    Sends a Web Push notification to all subscriptions associated with the given user_id.
    """
    db = get_db()
    
    # Get user document to check if notifications are enabled and get subscriptions
    user_ref = db.collection("users").document(user_id)
    user_doc = user_ref.get()
    
    if not user_doc.exists:
        return
        
    user_data = user_doc.to_dict()
    if not user_data.get("notifications_enabled", True):
        return
        
    subscriptions = user_data.get("push_subscriptions", [])
    if not subscriptions:
        return

    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon,
        "url": url
    })

    valid_subscriptions = []
    has_removals = False

    for sub in subscriptions:
        try:
            webpush(
                subscription_info=sub,
                data=payload,
                vapid_private_key=Config.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": f"mailto:{Config.VAPID_EMAIL}"}
            )
            valid_subscriptions.append(sub)
        except WebPushException as ex:
            logger.error(f"[Push Service] WebPushException sending to {user_id}: {repr(ex)}")
            # If the subscription is expired or invalid (e.g., 410 Gone), we should remove it.
            if ex.response is not None and ex.response.status_code in (404, 410):
                has_removals = True
            else:
                # Keep it if it's a temporary error
                valid_subscriptions.append(sub)
        except Exception as e:
            logger.error(f"[Push Service] Error sending push to {user_id}: {e}")
            valid_subscriptions.append(sub)

    # Clean up invalid subscriptions
    if has_removals:
        user_ref.update({"push_subscriptions": valid_subscriptions})
