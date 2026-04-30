import uuid
from datetime import datetime, timezone
from app.firebase import get_db


def create_notification(user_id: str, notif_type: str, message: str, metadata: dict = None):
    """Append a notification document for the given user."""
    db = get_db()
    notif_id = str(uuid.uuid4())
    doc = {
        "notification_id": notif_id,
        "user_id": user_id,
        "type": notif_type,
        "message": message,
        "read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if metadata:
        doc["metadata"] = metadata
    db.collection("notifications").document(notif_id).set(doc)

    # Trigger Web Push notification in the background
    try:
        from app.services.push_service import send_web_push
        import threading

        titles = {
            "clan_invite":             "New Clan Invite",
            "battle_challenge":        "Battle Challenge",
            "overtaken":               "Leaderboard Alert",
            "clan_behind":             "Clan Battle Alert",
            "clan_losing":             "Clan Battle Warning",
            "daily_summary":           "Daily Summary",
            "peer_activity":           "Friend Activity",
            "no_tasks_reminder":       "Morning Reminder",
            "plan_not_locked":         "Plan Reminder",
            "tasks_pending_reminder":  "Evening Reminder",
            "reached_top":             "Achievement Unlocked",
        }
        title = titles.get(notif_type, "XPForge Notification")

        # Capture Flask app object so the thread can push an app context.
        # This works whether called from a request context OR from the scheduler
        # (which now always runs inside app.app_context()).
        try:
            from flask import current_app
            app = current_app._get_current_object()
        except RuntimeError:
            app = None  # Should not happen now that scheduler uses app context

        def _push_with_context():
            try:
                if app is not None:
                    with app.app_context():
                        send_web_push(user_id, title, message)
                else:
                    # Last-resort: try without context (Firebase may still work)
                    send_web_push(user_id, title, message)
            except Exception as _e:
                import logging as _log
                _log.getLogger(__name__).error(f"Push thread error: {_e}")

        threading.Thread(target=_push_with_context, daemon=True).start()

    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"Error triggering push notification: {e}")

    return notif_id



def notify_overtaken(overtaken_user_id: str, overtaker_username: str):
    create_notification(
        overtaken_user_id,
        "overtaken",
        f"{overtaker_username} just passed you on the daily leaderboard!"
    )


def notify_clan_falling_behind(member_ids: list, rival_clan_name: str):
    for uid in member_ids:
        create_notification(
            uid,
            "clan_behind",
            f"Your clan is falling behind in the battle vs {rival_clan_name}."
        )


def notify_battle_challenge(leader_id: str, challenger_clan_name: str, battle_id: str, duration: str):
    create_notification(
        leader_id,
        "battle_challenge",
        f"{challenger_clan_name} has challenged your clan to a battle! ({duration})",
        metadata={
            "battle_id": battle_id,
            "challenger_clan_name": challenger_clan_name,
            "duration": duration,
        }
    )


def notify_daily_summary(user_id: str, xp_delta: int, rank: int, clan_summary: str = ""):
    msg = f"Day complete! XP: {'+' if xp_delta >= 0 else ''}{xp_delta} | Rank: #{rank}"
    if clan_summary:
        msg += f" | {clan_summary}"
    create_notification(user_id, "daily_summary", msg)


def notify_peer_tasks(user_id: str, peer_username: str, task_count: int):
    create_notification(
        user_id,
        "peer_activity",
        f"{peer_username} completed {task_count} task{'s' if task_count != 1 else ''} today."
    )


def notify_no_tasks_created(user_id: str):
    """Morning reminder: user hasn't created any planned tasks yet today."""
    create_notification(
        user_id,
        "no_tasks_reminder",
        "Morning check-in: You haven't planned your tasks for today yet. Lock in your goals now!"
    )


def notify_tasks_pending(user_id: str, pending_count: int):
    """Evening reminder: user has uncompleted planned tasks."""
    create_notification(
        user_id,
        "tasks_pending_reminder",
        f"You still have {pending_count} pending task{'s' if pending_count != 1 else ''} for today. Don't let the day slip away!"
    )


def notify_no_plan_locked(user_id: str, task_count: int):
    """Morning reminder: user has tasks but hasn't locked their plan yet."""
    create_notification(
        user_id,
        "plan_not_locked",
        f"You have {task_count} task{'s' if task_count != 1 else ''} but your plan is not locked yet. Lock it in to commit to your day!"
    )


def notify_clan_losing(user_id: str, rival_clan_name: str, our_avg: float, their_avg: float, battle_id: str = None):
    """Alert: user's clan is currently losing an active battle."""
    gap = round(their_avg - our_avg, 1)
    create_notification(
        user_id,
        "clan_losing",
        f"Your clan is losing the battle vs {rival_clan_name}! They lead by {gap} avg XP. Complete your tasks to catch up!",
        metadata={"battle_id": battle_id} if battle_id else None
    )


def notify_reached_top(user_id: str, period_label: str):
    """Celebration: user just hit #1 on a leaderboard."""
    create_notification(
        user_id,
        "reached_top",
        f"You are now #1 on the {period_label} leaderboard! You are the beast — keep the lead!"
    )
