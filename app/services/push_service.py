import json
import logging
from app.config import Config
from app.firebase import get_db

logger = logging.getLogger(__name__)


def send_web_push(user_id: str, title: str, body: str,
                  icon: str = "https://api.iconify.design/lucide/zap.svg?color=%236c63ff&width=192&height=192",
                  url: str = "/notifications.html"):
    """
    Sends a Web Push notification to all subscriptions associated with the given user_id.
    Safe to call from a background thread.
    """
    # Lazy import to avoid import-time failures if pywebpush not yet installed
    try:
        from pywebpush import webpush, WebPushException
    except ImportError:
        logger.error("[Push Service] pywebpush is not installed. Cannot send push notification.")
        return

    try:
        db = get_db()
    except Exception as e:
        logger.error(f"[Push Service] Could not get Firestore client: {e}")
        return

    try:
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
            # Strip fields pywebpush doesn't understand (e.g. expirationTime)
            clean_sub = {
                "endpoint": sub.get("endpoint", ""),
                "keys": sub.get("keys", {})
            }
            if not clean_sub["endpoint"] or not clean_sub["keys"]:
                has_removals = True
                continue

            try:
                webpush(
                    subscription_info=clean_sub,
                    data=payload,
                    vapid_private_key=Config.VAPID_PRIVATE_KEY,
                    vapid_claims={"sub": f"mailto:{Config.VAPID_EMAIL}"}
                )
                valid_subscriptions.append(sub)
            except WebPushException as ex:
                logger.error(f"[Push Service] WebPushException for {user_id}: {repr(ex)}")
                # 404/410 = subscription is expired/invalid — remove it
                if ex.response is not None and ex.response.status_code in (404, 410):
                    has_removals = True
                    logger.info(f"[Push Service] Removing expired subscription for {user_id}")
                else:
                    valid_subscriptions.append(sub)
            except Exception as e:
                logger.error(f"[Push Service] Unexpected error for {user_id}: {e}")
                valid_subscriptions.append(sub)

        # Clean up invalid subscriptions
        if has_removals:
            user_ref.update({"push_subscriptions": valid_subscriptions})

    except Exception as e:
        logger.error(f"[Push Service] Top-level error for user {user_id}: {e}")
