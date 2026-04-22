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


def morning_reminder_job():
    """
    Runs at 08:00 UTC.
    Two checks per user:
      1. No planned tasks at all  → notify_no_tasks_created
      2. Has tasks but plan not locked → notify_no_plan_locked
    Both are deduplicated (one per user per day).
    """
    logger.info("[Scheduler] Morning reminder job started.")
    try:
        import pytz
        from app.firebase import get_db
        from app.services.notification_service import (
            notify_no_tasks_created,
            notify_no_plan_locked,
        )

        db = get_db()
        all_users = db.collection("users").get()

        for user_doc in all_users:
            try:
                user_data = user_doc.to_dict()
                user_id   = user_data.get("user_id") or user_doc.id
                tz_str    = user_data.get("timezone", "UTC")

                try:
                    tz = pytz.timezone(tz_str)
                except Exception:
                    tz = pytz.utc

                today = datetime.now(tz).strftime("%Y-%m-%d")

                # ── Fetch today's tasks once ──────────────────────────────
                tasks_today = (
                    db.collection("tasks")
                    .where("user_id", "==", user_id)
                    .where("date", "==", today)
                    .where("type", "==", "planned")
                    .get()
                )

                if not tasks_today:
                    # Check 1: no tasks at all
                    already = (
                        db.collection("notifications")
                        .where("user_id", "==", user_id)
                        .where("type", "==", "no_tasks_reminder")
                        .get()
                    )
                    if not any(d.to_dict().get("created_at", "")[:10] == today for d in already):
                        notify_no_tasks_created(user_id)
                else:
                    # Check 2: tasks exist but plan is not locked yet
                    plan_docs = (
                        db.collection("daily_plans")
                        .where("user_id", "==", user_id)
                        .where("date", "==", today)
                        .limit(1)
                        .get()
                    )
                    plan_locked = plan_docs and plan_docs[0].to_dict().get("locked", False)
                    if not plan_locked:
                        already = (
                            db.collection("notifications")
                            .where("user_id", "==", user_id)
                            .where("type", "==", "plan_not_locked")
                            .get()
                        )
                        if not any(d.to_dict().get("created_at", "")[:10] == today for d in already):
                            notify_no_plan_locked(user_id, len(tasks_today))

            except Exception as e:
                logger.warning(f"[Scheduler] Morning reminder failed for user {user_doc.id}: {e}")

    except Exception as e:
        logger.error(f"[Scheduler] Morning reminder job error: {e}")

    logger.info("[Scheduler] Morning reminder job complete.")


def evening_reminder_job():
    """
    Runs at 20:00 UTC.
    Notifies users who have pending planned tasks for today.
    Deduplicated: skips users who already received this notification today.
    """
    logger.info("[Scheduler] Evening reminder job started.")
    try:
        import pytz
        from app.firebase import get_db
        from app.services.notification_service import notify_tasks_pending

        db = get_db()
        now_utc = datetime.now(timezone.utc)
        all_users = db.collection("users").get()

        for user_doc in all_users:
            try:
                user_data = user_doc.to_dict()
                user_id   = user_data.get("user_id") or user_doc.id
                tz_str    = user_data.get("timezone", "UTC")

                try:
                    tz = pytz.timezone(tz_str)
                except Exception:
                    tz = pytz.utc

                today = datetime.now(tz).strftime("%Y-%m-%d")

                # Skip if user already got this reminder today (dedup)
                existing = (
                    db.collection("notifications")
                    .where("user_id", "==", user_id)
                    .where("type", "==", "tasks_pending_reminder")
                    .get()
                )
                if any(d.to_dict().get("created_at", "")[:10] == today for d in existing):
                    continue

                # Count pending planned tasks for today
                pending_tasks = (
                    db.collection("tasks")
                    .where("user_id", "==", user_id)
                    .where("date", "==", today)
                    .where("type", "==", "planned")
                    .where("status", "==", "pending")
                    .get()
                )
                if pending_tasks:
                    notify_tasks_pending(user_id, len(pending_tasks))

            except Exception as e:
                logger.warning(f"[Scheduler] Evening reminder failed for user {user_doc.id}: {e}")

    except Exception as e:
        logger.error(f"[Scheduler] Evening reminder job error: {e}")

    logger.info("[Scheduler] Evening reminder job complete.")


def battle_check_job():
    """
    Runs every hour.
    For every active clan battle, compares average XP of both clans.
    Notifies each member of the losing clan once per battle per day.
    Deduplication key: type='clan_losing', metadata.battle_id, date today.
    """
    logger.info("[Scheduler] Battle check job started.")
    try:
        from app.firebase import get_db
        from app.services.notification_service import notify_clan_losing
        from datetime import datetime, timezone

        db  = get_db()
        now = datetime.now(timezone.utc)
        today_str = now.strftime("%Y-%m-%d")

        active_battles = (
            db.collection("clan_battles")
            .where("status", "==", "active")
            .get()
        )

        for battle_doc in active_battles:
            try:
                bd         = battle_doc.to_dict()
                battle_id  = battle_doc.id
                clan_a_id  = bd.get("clan_a_id")
                clan_b_id  = bd.get("clan_b_id")

                def _avg_xp(clan_id):
                    c = db.collection("clans").document(clan_id).get()
                    if not c.exists:
                        return 0, []
                    data    = c.to_dict()
                    members = data.get("member_ids", [])
                    if not members:
                        return 0, members
                    total = sum(
                        (db.collection("users").document(uid).get().to_dict() or {}).get("total_xp", 0)
                        for uid in members
                    )
                    return total / len(members), members, data.get("name", "Rival Clan")

                result_a = _avg_xp(clan_a_id)
                result_b = _avg_xp(clan_b_id)
                avg_a, members_a, name_a = result_a if len(result_a) == 3 else (result_a[0], result_a[1], "Rival Clan")
                avg_b, members_b, name_b = result_b if len(result_b) == 3 else (result_b[0], result_b[1], "Rival Clan")

                # Determine which clan is losing
                if avg_a >= avg_b:
                    losing_members = members_b
                    rival_name     = name_a
                    our_avg        = avg_b
                    their_avg      = avg_a
                else:
                    losing_members = members_a
                    rival_name     = name_b
                    our_avg        = avg_a
                    their_avg      = avg_b

                # Only notify if there's a meaningful gap (at least 1 XP)
                if their_avg - our_avg < 1:
                    continue

                for uid in losing_members:
                    try:
                        # Dedup: one clan_losing notification per battle per day
                        existing = (
                            db.collection("notifications")
                            .where("user_id", "==", uid)
                            .where("type", "==", "clan_losing")
                            .get()
                        )
                        already_notified = any(
                            d.to_dict().get("created_at", "")[:10] == today_str and
                            (d.to_dict().get("metadata") or {}).get("battle_id") == battle_id
                            for d in existing
                        )
                        if not already_notified:
                            notify_clan_losing(uid, rival_name, our_avg, their_avg, battle_id=battle_id)
                    except Exception as e:
                        logger.warning(f"[Scheduler] Battle check notify failed for user {uid}: {e}")

            except Exception as e:
                logger.warning(f"[Scheduler] Battle check failed for battle {battle_doc.id}: {e}")

    except Exception as e:
        logger.error(f"[Scheduler] Battle check job error: {e}")

    logger.info("[Scheduler] Battle check job complete.")


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
    scheduler.add_job(
        func=morning_reminder_job,
        trigger=CronTrigger(hour=8, minute=0, second=0, timezone="UTC"),
        id="morning_reminder_job",
        name="Morning task + lock reminder",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        func=evening_reminder_job,
        trigger=CronTrigger(hour=20, minute=0, second=0, timezone="UTC"),
        id="evening_reminder_job",
        name="Evening pending tasks reminder",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.add_job(
        func=battle_check_job,
        trigger=CronTrigger(minute=0, second=0, timezone="UTC"),  # every hour
        id="battle_check_job",
        name="Hourly clan battle loss check",
        replace_existing=True,
        misfire_grace_time=300,
    )
    scheduler.start()
    logger.info("[Scheduler] APScheduler started. Jobs: midnight(00:00), morning(08:00), evening(20:00), battle-check(hourly) UTC.")

    import atexit
    atexit.register(lambda: scheduler.shutdown(wait=False))

