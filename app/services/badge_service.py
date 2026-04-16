"""
Badge service — all badge assignment logic lives here.
Called by the midnight scheduler and clan battle finalization.
"""
from datetime import datetime, timezone
from app.firebase import get_db


BADGE_BEAST = {"id": "beast", "name": "Beast", "icon": "flame", "description": "Highest XP of the day"}
BADGE_SLACKER = {"id": "slacker", "name": "Slacker", "icon": "moon", "description": "Most negative XP of the day"}
BADGE_WARCHIEF = {"id": "warchief", "name": "Warchief", "icon": "swords", "description": "Clan battle winner"}
BADGE_COMMITTED = {"id": "committed", "name": "Committed", "icon": "lock", "description": "Locked plan 7 days in a row"}
BADGE_GHOST = {"id": "ghost", "name": "Ghost", "icon": "ghost", "description": "No activity for 3+ consecutive days"}


def _add_badge(db, user_id: str, badge: dict):
    """Add a badge to the user's badges array if not already present for today."""
    user_ref = db.collection("users").document(user_id)
    user = user_ref.get()
    if not user.exists:
        return
    badges = user.to_dict().get("badges", [])
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # Add with awarded_date for tracking
    badge_entry = {**badge, "awarded_at": today}
    # Avoid exact duplicate for same badge on same day
    already = any(b.get("id") == badge["id"] and b.get("awarded_at") == today for b in badges)
    if not already:
        badges.append(badge_entry)
        user_ref.update({"badges": badges})


def assign_beast_badge(user_id: str):
    db = get_db()
    _add_badge(db, user_id, BADGE_BEAST)


def assign_slacker_badge(user_id: str):
    db = get_db()
    _add_badge(db, user_id, BADGE_SLACKER)


def assign_warchief_badge(member_ids: list):
    db = get_db()
    for uid in member_ids:
        _add_badge(db, uid, BADGE_WARCHIEF)


def assign_committed_badge(user_id: str):
    db = get_db()
    _add_badge(db, user_id, BADGE_COMMITTED)


def assign_ghost_badge(user_id: str):
    db = get_db()
    _add_badge(db, user_id, BADGE_GHOST)


def check_committed_streak(user_id: str) -> bool:
    """Return True if user has locked their plan every day for the past 7 days."""
    from datetime import timedelta
    db = get_db()
    today = datetime.now(timezone.utc).date()
    for i in range(7):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        plans = (
            db.collection("daily_plans")
            .where("user_id", "==", user_id)
            .where("date", "==", date_str)
            .where("locked", "==", True)
            .limit(1)
            .get()
        )
        if not plans:
            return False
    return True


def check_ghost_status(user_id: str) -> bool:
    """Return True if user has had no completed tasks in the last 3 days."""
    from datetime import timedelta
    db = get_db()
    today = datetime.now(timezone.utc).date()
    for i in range(3):
        date_str = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        tasks = (
            db.collection("tasks")
            .where("user_id", "==", user_id)
            .where("date", "==", date_str)
            .where("status", "==", "completed")
            .limit(1)
            .get()
        )
        if tasks:
            return False
    return True
