"""
Leaderboard service — manages all 5 leaderboard period types.
Path convention: leaderboards/{period_type}/{period_key}/entries/{user_id}
"""
from datetime import datetime, timezone
import pytz
from app.firebase import get_db

PERIOD_TYPES = ["daily", "weekly", "monthly", "yearly", "global"]


def _period_key(period_type: str) -> str:
    now = datetime.now(timezone.utc)
    if period_type == "daily":
        return now.strftime("%Y-%m-%d")
    elif period_type == "weekly":
        iso = now.isocalendar()
        return f"{iso[0]}-W{iso[1]:02d}"
    elif period_type == "monthly":
        return now.strftime("%Y-%m")
    elif period_type == "yearly":
        return now.strftime("%Y")
    else:  # global
        return "all-time"


def update_all_leaderboards(user_id: str, xp_delta: int, username: str, avatar_color: str):
    """Update all 5 leaderboard entries for a user by xp_delta."""
    db = get_db()
    for period_type in PERIOD_TYPES:
        key = _period_key(period_type)
        ref = (
            db.collection("leaderboards")
            .document(period_type)
            .collection(key)
            .document(user_id)
        )
        doc = ref.get()
        if doc.exists:
            current_xp = doc.to_dict().get("xp", 0)
            ref.update({"xp": current_xp + xp_delta, "username": username, "avatar_color": avatar_color})
        else:
            ref.set({
                "user_id": user_id,
                "username": username,
                "avatar_color": avatar_color,
                "xp": xp_delta,
                "rank": 0,  # rank is computed at read time
            })


def get_leaderboard(period_type: str, period_key_override: str = None) -> list:
    """
    Fetch and return a sorted leaderboard for the given period.
    Returns list of entries sorted by XP descending, with rank assigned.
    """
    db = get_db()
    key = period_key_override or _period_key(period_type)
    docs = (
        db.collection("leaderboards")
        .document(period_type)
        .collection(key)
        .get()
    )
    entries = [d.to_dict() for d in docs]
    entries.sort(key=lambda e: e.get("xp", 0), reverse=True)
    for i, entry in enumerate(entries):
        entry["rank"] = i + 1
    return entries


def get_current_period_key(period_type: str) -> str:
    return _period_key(period_type)


def reset_daily_leaderboard(date_key: str):
    """Called by midnight job — archives then removes daily entries for the given date."""
    # Entries are archived by keeping the historical subcollection intact.
    # A new date automatically creates a fresh subcollection the next day.
    pass  # Firestore auto-creates new subcollection per new date key — no action needed.


def get_clan_leaderboard(clan_id: str) -> list:
    """Return leaderboard entries for all members of a clan, sorted by total_xp."""
    db = get_db()
    clan_doc = db.collection("clans").document(clan_id).get()
    if not clan_doc.exists:
        return []
    member_ids = clan_doc.to_dict().get("member_ids", [])
    entries = []
    for uid in member_ids:
        user_doc = db.collection("users").document(uid).get()
        if user_doc.exists:
            u = user_doc.to_dict()
            entries.append({
                "user_id": uid,
                "username": u.get("username", ""),
                "avatar_color": u.get("avatar_color", "#6C63FF"),
                "xp": u.get("total_xp", 0),
                "badges": u.get("badges", []),
            })
    entries.sort(key=lambda e: e.get("xp", 0), reverse=True)
    for i, e in enumerate(entries):
        e["rank"] = i + 1
    return entries
