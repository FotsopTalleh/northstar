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
        "⏰ Morning check-in: You haven't planned your tasks for today yet. Lock in your goals now!"
    )


def notify_tasks_pending(user_id: str, pending_count: int):
    """Evening reminder: user has uncompleted planned tasks."""
    create_notification(
        user_id,
        "tasks_pending_reminder",
        f"⚡ Heads up! You still have {pending_count} pending task{'s' if pending_count != 1 else ''} for today. Don't let the day slip away!"
    )
