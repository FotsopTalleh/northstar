import logging
from app.firebase import get_db

logger = logging.getLogger(__name__)


def send_web_push(user_id: str, title: str, body: str,
                  icon: str = "https://api.iconify.design/lucide/zap.svg?color=%236c63ff&width=192&height=192",
                  url: str = "/notifications.html"):
    """
    Sends a Firebase Cloud Messaging (FCM) push notification to all registered
    FCM tokens for the given user_id.

    Tokens are stored in users/{user_id}.fcm_tokens as a list of strings.
    Falls back to the legacy push_subscriptions list if no FCM tokens present.
    """
    try:
        from firebase_admin import messaging
    except ImportError:
        logger.error("[FCM] firebase_admin is not installed.")
        return

    try:
        db = get_db()
    except Exception as e:
        logger.error(f"[FCM] Could not get Firestore client: {e}")
        return

    try:
        user_ref = db.collection("users").document(user_id)
        user_doc = user_ref.get()

        if not user_doc.exists:
            return

        user_data = user_doc.to_dict()
        if not user_data.get("notifications_enabled", True):
            return

        tokens = user_data.get("fcm_tokens", [])
        if not tokens:
            logger.debug(f"[FCM] No FCM tokens for user {user_id}.")
            return

        valid_tokens = []
        for token in tokens:
            if not token or not isinstance(token, str):
                continue
            try:
                message = messaging.Message(
                    notification=messaging.Notification(
                        title=title,
                        body=body,
                    ),
                    webpush=messaging.WebpushConfig(
                        notification=messaging.WebpushNotification(
                            title=title,
                            body=body,
                            icon=icon,
                        ),
                        fcm_options=messaging.WebpushFCMOptions(
                            link=url,
                        ),
                    ),
                    token=token,
                )
                response = messaging.send(message)
                logger.info(f"[FCM] Sent to {user_id}: {response}")
                valid_tokens.append(token)
            except messaging.UnregisteredError:
                logger.info(f"[FCM] Token expired/unregistered for {user_id} — removing.")
            except messaging.SenderIdMismatchError:
                logger.warning(f"[FCM] Sender ID mismatch for {user_id} — removing token.")
            except Exception as e:
                logger.error(f"[FCM] Error sending to {user_id}: {e}")
                valid_tokens.append(token)  # Keep on unknown errors

        # Prune stale tokens
        if len(valid_tokens) != len(tokens):
            user_ref.update({"fcm_tokens": valid_tokens})

    except Exception as e:
        logger.error(f"[FCM] Top-level error for user {user_id}: {e}")
