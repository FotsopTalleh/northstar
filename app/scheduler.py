"""
APScheduler midnight job — runs at 00:00 UTC daily.
Handles: auto-fail, XP finalization, leaderboard archiving, badge assignment, battle finalization, notifications.
"""
import logging
from datetime import datetime, timezone, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)


def midnight_job():
    """The main nightly finalization job."""
    logger.info("[Scheduler] Midnight job started.")
    from app.firebase import get_db
    from app.services.xp_service import finalize_xp_for_task, PLANNED_FAIL_XP
    from app.services.leaderboard_service import get_leaderboard, get_current_period_key
    from app.services.badge_service import (
        assign_beast_badge, assign_slacker_badge,
        assign_warchief_badge, assign_committed_badge,
        assign_ghost_badge, check_committed_streak, check_ghost_status
    )
    from app.services.notification_service import (
        notify_daily_summary, notify_peer_tasks
    )

    db = get_db()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    # ── Step 1: Auto-fail all unmarked planned tasks from yesterday ──────────
    locked_plans = (
        db.collection("daily_plans")
        .where("date", "==", yesterday)
        .where("locked", "==", True)
        .get()
    )

    affected_users = set()
    for plan_doc in locked_plans:
        plan_data = plan_doc.to_dict()
        user_id = plan_data["user_id"]
        affected_users.add(user_id)

        pending_tasks = (
            db.collection("tasks")
            .where("plan_id", "==", plan_doc.id)
            .where("status", "==", "pending")
            .where("type", "==", "planned")
            .get()
        )
        for task_doc in pending_tasks:
            task_id = task_doc.id
            task_doc.reference.update({"status": "failed"})
            finalize_xp_for_task(user_id, task_id, PLANNED_FAIL_XP, "Planned task auto-failed at midnight")

    logger.info(f"[Scheduler] Auto-failed pending tasks for {len(locked_plans)} plans.")

    # ── Step 2: Finalize provisional XP log entries ──────────────────────────
    provisional_logs = (
        db.collection("xp_logs")
        .where("is_provisional", "==", True)
        .get()
    )
    batch = db.batch()
    for log_doc in provisional_logs:
        batch.update(log_doc.reference, {"is_provisional": False})
    batch.commit()
    logger.info(f"[Scheduler] Finalized {len(provisional_logs)} provisional XP entries.")

    # ── Step 3: Determine daily Beast and Slacker ────────────────────────────
    daily_key = yesterday
    daily_entries = get_leaderboard("daily", period_key_override=daily_key)

    if daily_entries:
        beast_entry = daily_entries[0]
        slacker_entry = daily_entries[-1]
        assign_beast_badge(beast_entry["user_id"])
        assign_slacker_badge(slacker_entry["user_id"])
        logger.info(f"[Scheduler] Beast: {beast_entry.get('username')} | Slacker: {slacker_entry.get('username')}")

    # ── Step 4: Daily summary notifications ─────────────────────────────────
    rank_map = {e["user_id"]: e["rank"] for e in daily_entries}
    xp_map = {e["user_id"]: e.get("xp", 0) for e in daily_entries}

    for user_id in affected_users:
        rank = rank_map.get(user_id, 0)
        xp = xp_map.get(user_id, 0)
        notify_daily_summary(user_id, xp, rank)

    # Peer task summary (once per day per clan mate)
    for user_id in affected_users:
        user = db.collection("users").document(user_id).get()
        if not user.exists:
            continue
        clan_id = user.to_dict().get("clan_id")
        if not clan_id:
            continue
        clan = db.collection("clans").document(clan_id).get()
        if not clan.exists:
            continue
        for member_id in clan.to_dict().get("member_ids", []):
            if member_id == user_id:
                continue
            completed = (
                db.collection("tasks")
                .where("user_id", "==", member_id)
                .where("date", "==", yesterday)
                .where("status", "==", "completed")
                .get()
            )
            if completed:
                member_data = db.collection("users").document(member_id).get().to_dict() or {}
                notify_peer_tasks(user_id, member_data.get("username", "Someone"), len(completed))

    # ── Step 5: Check Ghost and Committed badges for all active users ────────
    all_users = db.collection("users").get()
    for user_doc in all_users:
        uid = user_doc.id
        if check_ghost_status(uid):
            assign_ghost_badge(uid)
        if check_committed_streak(uid):
            assign_committed_badge(uid)

    # ── Step 6: Finalize completed clan battles ──────────────────────────────
    now_iso = datetime.now(timezone.utc).isoformat()
    active_battles = (
        db.collection("clan_battles")
        .where("status", "==", "active")
        .get()
    )
    for battle_doc in active_battles:
        bd = battle_doc.to_dict()
        if bd.get("end_at", "9999") > now_iso:
            continue

        # Compute avg XP for each clan
        def avg_xp_for_clan(clan_id):
            clan = db.collection("clans").document(clan_id).get()
            if not clan.exists:
                return 0
            members = clan.to_dict().get("member_ids", [])
            if not members:
                return 0
            total = sum(
                db.collection("users").document(uid).get().to_dict().get("total_xp", 0)
                for uid in members
            )
            return total / len(members)

        avg_a = avg_xp_for_clan(bd["clan_a_id"])
        avg_b = avg_xp_for_clan(bd["clan_b_id"])
        winner_id = bd["clan_a_id"] if avg_a >= avg_b else bd["clan_b_id"]

        battle_doc.reference.update({
            "status": "completed",
            "winner_clan_id": winner_id,
            "avg_xp_a": round(avg_a, 2),
            "avg_xp_b": round(avg_b, 2),
        })

        # Award Warchief badge to all winning clan members
        winner_clan = db.collection("clans").document(winner_id).get()
        if winner_clan.exists:
            assign_warchief_badge(winner_clan.to_dict().get("member_ids", []))

        logger.info(f"[Scheduler] Battle {battle_doc.id} completed. Winner: {winner_id}")

    logger.info("[Scheduler] Midnight job complete.")


def start_scheduler(app):
    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        func=midnight_job,
        trigger=CronTrigger(hour=0, minute=0, second=0, timezone="UTC"),
        id="midnight_job",
        name="Midnight finalization",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    logger.info("[Scheduler] APScheduler started. Midnight job scheduled at 00:00 UTC.")

    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))
