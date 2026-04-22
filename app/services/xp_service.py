"""
XP Service — the single source of truth for all XP calculations.
No XP math happens anywhere else in the system.
"""
import uuid
from datetime import datetime, timezone
from app.firebase import get_db
from app.services.leaderboard_service import update_all_leaderboards

# XP Constants
PLANNED_COMPLETE_XP = 7
PLANNED_FAIL_XP = -4
UNPLANNED_COMPLETE_XP = 3


def _has_xp_log_for_task(db, task_id: str) -> bool:
    """Duplicate guard: check if an XP log already exists for this task."""
    logs = (
        db.collection("xp_logs")
        .where("task_id", "==", task_id)
        .limit(1)
        .get()
    )
    return len(logs) > 0


def _append_xp_log(db, user_id: str, task_id: str, xp_delta: int, reason: str, is_provisional: bool = True) -> str:
    """Append an immutable XP log entry. Never updates or deletes existing entries."""
    log_id = str(uuid.uuid4())
    db.collection("xp_logs").document(log_id).set({
        "log_id": log_id,
        "user_id": user_id,
        "task_id": task_id,
        "xp_delta": xp_delta,
        "reason": reason,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "is_provisional": is_provisional,
    })
    return log_id


def _snapshot_daily_ranks() -> dict:
    """Return {user_id: rank} for the current daily leaderboard. Lightweight — one Firestore read."""
    from app.services.leaderboard_service import get_leaderboard
    entries = get_leaderboard("daily")
    return {e["user_id"]: e["rank"] for e in entries}


def award_provisional_xp(user_id: str, task_id: str, task_type: str) -> dict:
    """
    Award provisional XP when a task is completed.
    Returns {"xp_delta": int, "new_total": int}
    """
    db = get_db()

    if _has_xp_log_for_task(db, task_id):
        raise ValueError("XP already awarded for this task")

    xp_delta = PLANNED_COMPLETE_XP if task_type == "planned" else UNPLANNED_COMPLETE_XP
    reason = f"{'Planned' if task_type == 'planned' else 'Unplanned'} task completed (provisional)"

    # ── Snapshot ranks BEFORE the update ─────────────────────────────────────
    try:
        ranks_before = _snapshot_daily_ranks()
        my_rank_before = ranks_before.get(user_id, 9999)
    except Exception:
        ranks_before = {}
        my_rank_before = 9999

    # Append log
    _append_xp_log(db, user_id, task_id, xp_delta, reason, is_provisional=True)

    # Update user total_xp
    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get().to_dict()
    new_total = user_data.get("total_xp", 0) + xp_delta
    user_ref.update({"total_xp": new_total})

    # Update leaderboards provisionally
    update_all_leaderboards(user_id, xp_delta, user_data.get("username", ""), user_data.get("avatar_color", "#6C63FF"))

    # ── Rank-change notifications ─────────────────────────────────────────────
    try:
        from app.services.notification_service import notify_overtaken, notify_reached_top
        ranks_after  = _snapshot_daily_ranks()
        my_rank_after = ranks_after.get(user_id, 9999)

        if my_rank_after < my_rank_before:
            my_username = user_data.get("username", "Someone")

            # Notify every user whose old rank sat between my new and old rank —
            # those are exactly the people I leapfrogged.
            for uid, old_rank in ranks_before.items():
                if uid == user_id:
                    continue
                if my_rank_after <= old_rank < my_rank_before:
                    notify_overtaken(uid, my_username)

            # Celebrate reaching #1 on the daily board
            if my_rank_after == 1 and my_rank_before != 1:
                notify_reached_top(user_id, "daily")
    except Exception:
        pass  # Never let notification errors break XP award

    return {"xp_delta": xp_delta, "new_total": new_total}


def deduct_provisional_xp(user_id: str, task_id: str) -> dict:
    """
    Deduct XP when a planned task is manually failed.
    """
    db = get_db()

    if _has_xp_log_for_task(db, task_id):
        raise ValueError("XP already recorded for this task")

    xp_delta = PLANNED_FAIL_XP
    reason = "Planned task manually failed (provisional)"

    _append_xp_log(db, user_id, task_id, xp_delta, reason, is_provisional=True)

    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get().to_dict()
    new_total = user_data.get("total_xp", 0) + xp_delta
    user_ref.update({"total_xp": new_total})

    update_all_leaderboards(user_id, xp_delta, user_data.get("username", ""), user_data.get("avatar_color", "#6C63FF"))

    return {"xp_delta": xp_delta, "new_total": new_total}


def finalize_xp_for_task(user_id: str, task_id: str, xp_delta: int, reason: str):
    """
    Called by the midnight scheduler for auto-failed tasks.
    Writes a new finalized (non-provisional) XP log entry.
    """
    db = get_db()

    if _has_xp_log_for_task(db, task_id):
        # Already has a provisional entry from manual action — do not double-count
        return

    _append_xp_log(db, user_id, task_id, xp_delta, reason, is_provisional=False)

    user_ref = db.collection("users").document(user_id)
    user_data = user_ref.get().to_dict()
    new_total = user_data.get("total_xp", 0) + xp_delta
    user_ref.update({"total_xp": new_total})

    update_all_leaderboards(user_id, xp_delta, user_data.get("username", ""), user_data.get("avatar_color", "#6C63FF"))


def get_user_xp_logs(user_id: str, limit: int = 50) -> list:
    db = get_db()
    logs = (
        db.collection("xp_logs")
        .where("user_id", "==", user_id)
        .get()
    )
    log_dicts = [l.to_dict() for l in logs]
    log_dicts.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    return log_dicts[:limit]
