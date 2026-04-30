import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
import pytz
from app.firebase import get_db
from app.middleware import require_auth
from app.services.xp_service import award_provisional_xp, deduct_provisional_xp

task_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")

MAX_PLANNED = 10
MAX_UNPLANNED = 5

CARRY_OVER_XP = -2   # XP penalty for carrying a task to the next day


def _get_today_for_user(tz_str: str) -> str:
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.utc
    return datetime.now(tz).strftime("%Y-%m-%d")


def _get_tomorrow_for_user(tz_str: str) -> str:
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.utc
    return (datetime.now(tz) + timedelta(days=1)).strftime("%Y-%m-%d")


@task_bp.route("/add", methods=["POST"])
@require_auth
def add_task():
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    task_type = data.get("type", "planned")

    if not title:
        return jsonify({"error": "Task title is required"}), 400
    if task_type not in ("planned", "unplanned"):
        return jsonify({"error": "type must be 'planned' or 'unplanned'"}), 400

    db = get_db()
    user_ref = db.collection("users").document(g.user_id)
    user = user_ref.get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404

    tz_str = user.to_dict().get("timezone", "UTC")
    today = _get_today_for_user(tz_str)

    # Load today's plan
    plans = (
        db.collection("daily_plans")
        .where("user_id", "==", g.user_id)
        .where("date", "==", today)
        .limit(1)
        .get()
    )

    plan_id = None
    plan_locked = False

    if plans:
        plan_doc = plans[0]
        plan_id = plan_doc.id
        plan_locked = plan_doc.to_dict().get("locked", False)

    # Enforce: no planned tasks after lock
    if task_type == "planned" and plan_locked:
        return jsonify({"error": "Cannot add planned tasks after the plan is locked"}), 403

    # Count existing tasks of this type today
    existing = (
        db.collection("tasks")
        .where("user_id", "==", g.user_id)
        .where("date", "==", today)
        .where("type", "==", task_type)
        .get()
    )
    count = len(existing)

    if task_type == "planned" and count >= MAX_PLANNED:
        return jsonify({"error": f"Maximum {MAX_PLANNED} planned tasks per day"}), 400
    if task_type == "unplanned" and count >= MAX_UNPLANNED:
        return jsonify({"error": f"Maximum {MAX_UNPLANNED} unplanned tasks per day"}), 400

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    task_doc = {
        "task_id": task_id,
        "user_id": g.user_id,
        "plan_id": plan_id if task_type == "planned" else None,
        "title": title,
        "type": task_type,
        "status": "pending",
        "date": today,
        "created_at": now,
        "completed_at": None,
        "xp_awarded": None,
    }
    db.collection("tasks").document(task_id).set(task_doc)
    return jsonify(task_doc), 201


@task_bp.route("/<task_id>/complete", methods=["PATCH"])
@require_auth
def complete_task(task_id):
    db = get_db()
    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()

    if not task_doc.exists:
        return jsonify({"error": "Task not found"}), 404

    task = task_doc.to_dict()
    if task["user_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    if task["status"] != "pending":
        return jsonify({"error": f"Task is already {task['status']}"}), 409

    now = datetime.now(timezone.utc).isoformat()
    task_ref.update({"status": "completed", "completed_at": now})

    try:
        result = award_provisional_xp(g.user_id, task_id, task["type"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    task_ref.update({"xp_awarded": result["xp_delta"]})

    return jsonify({
        "message": "Task completed",
        "xp_delta": result["xp_delta"],
        "new_total_xp": result["new_total"],
    }), 200


@task_bp.route("/<task_id>/fail", methods=["PATCH"])
@require_auth
def fail_task(task_id):
    db = get_db()
    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()

    if not task_doc.exists:
        return jsonify({"error": "Task not found"}), 404

    task = task_doc.to_dict()
    if task["user_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    if task["status"] != "pending":
        return jsonify({"error": f"Task is already {task['status']}"}), 409
    if task["type"] != "planned":
        return jsonify({"error": "Only planned tasks can be manually failed"}), 400

    task_ref.update({"status": "failed"})

    try:
        result = deduct_provisional_xp(g.user_id, task_id)
    except ValueError as e:
        return jsonify({"error": str(e)}), 409

    task_ref.update({"xp_awarded": result["xp_delta"]})

    return jsonify({
        "message": "Task failed",
        "xp_delta": result["xp_delta"],
        "new_total_xp": result["new_total"],
    }), 200


# ─── SCHEDULE FOR TOMORROW ──────────────────────────────────────────────────
@task_bp.route("/schedule-tomorrow", methods=["POST"])
@require_auth
def schedule_tomorrow():
    """Add a planned task directly to tomorrow's date (not today)."""
    data = request.get_json(silent=True) or {}
    title = data.get("title", "").strip()
    if not title:
        return jsonify({"error": "Task title is required"}), 400

    db = get_db()
    user_ref = db.collection("users").document(g.user_id)
    user = user_ref.get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404

    tz_str = user.to_dict().get("timezone", "UTC")
    tomorrow = _get_tomorrow_for_user(tz_str)

    # Count existing planned tasks for tomorrow
    existing = (
        db.collection("tasks")
        .where("user_id", "==", g.user_id)
        .where("date", "==", tomorrow)
        .where("type", "==", "planned")
        .get()
    )
    if len(existing) >= MAX_PLANNED:
        return jsonify({"error": f"Maximum {MAX_PLANNED} planned tasks already scheduled for tomorrow"}), 400

    task_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    task_doc = {
        "task_id": task_id,
        "user_id": g.user_id,
        "plan_id": None,  # plan will be created/linked at the start of tomorrow
        "title": title,
        "type": "planned",
        "status": "pending",
        "date": tomorrow,
        "created_at": now,
        "completed_at": None,
        "xp_awarded": None,
        "scheduled_from_today": True,
    }
    db.collection("tasks").document(task_id).set(task_doc)
    return jsonify({**task_doc, "scheduled_for": tomorrow}), 201


# ─── CARRY OVER TO TOMORROW (−2 XP penalty) ─────────────────────────────────
@task_bp.route("/<task_id>/carry-over", methods=["POST"])
@require_auth
def carry_over(task_id):
    """
    Carry a pending planned task to tomorrow.
    Applies a -2 XP penalty immediately.
    The original task is marked 'carried_over' and a new clone is created for tomorrow.
    """
    db = get_db()
    task_ref = db.collection("tasks").document(task_id)
    task_doc = task_ref.get()

    if not task_doc.exists:
        return jsonify({"error": "Task not found"}), 404

    task = task_doc.to_dict()
    if task["user_id"] != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    if task["status"] != "pending":
        return jsonify({"error": f"Only pending tasks can be carried over (task is '{task['status']}')"}), 409
    if task["type"] != "planned":
        return jsonify({"error": "Only planned tasks can be carried over"}), 400

    # Check if already carried over today (prevent double carry)
    if task.get("carried_over"):
        return jsonify({"error": "This task has already been carried over"}), 409

    user_ref = db.collection("users").document(g.user_id)
    user_data = user_ref.get().to_dict()
    tz_str = user_data.get("timezone", "UTC")
    tomorrow = _get_tomorrow_for_user(tz_str)

    # Count existing planned tasks for tomorrow
    existing_tomorrow = (
        db.collection("tasks")
        .where("user_id", "==", g.user_id)
        .where("date", "==", tomorrow)
        .where("type", "==", "planned")
        .get()
    )
    if len(existing_tomorrow) >= MAX_PLANNED:
        return jsonify({"error": f"Tomorrow already has {MAX_PLANNED} planned tasks. Cannot carry over."}), 400

    # Apply -2 XP penalty
    from app.services.leaderboard_service import update_all_leaderboards as _ualb

    now_iso = datetime.now(timezone.utc).isoformat()
    penalty_log_id = str(uuid.uuid4())

    # Write XP log for the carry-over penalty (non-provisional, takes effect immediately)
    db.collection("xp_logs").document(penalty_log_id).set({
        "log_id": penalty_log_id,
        "user_id": g.user_id,
        "task_id": task_id,
        "xp_delta": CARRY_OVER_XP,
        "reason": f"Task carried over to {tomorrow} (−2 XP penalty)",
        "timestamp": now_iso,
        "is_provisional": False,
    })

    new_total = user_data.get("total_xp", 0) + CARRY_OVER_XP
    user_ref.update({"total_xp": new_total})
    _ualb(g.user_id, CARRY_OVER_XP, user_data.get("username", ""), user_data.get("avatar_color", "#6C63FF"))

    # Mark original task as carried over
    task_ref.update({
        "status": "carried_over",
        "xp_awarded": CARRY_OVER_XP,
        "carried_over": True,
        "carry_over_date": tomorrow,
    })

    # Clone task for tomorrow
    new_task_id = str(uuid.uuid4())
    new_task = {
        "task_id": new_task_id,
        "user_id": g.user_id,
        "plan_id": None,
        "title": task["title"],
        "type": "planned",
        "status": "pending",
        "date": tomorrow,
        "created_at": now_iso,
        "completed_at": None,
        "xp_awarded": None,
        "carried_from_task_id": task_id,
    }
    db.collection("tasks").document(new_task_id).set(new_task)

    return jsonify({
        "message": f"Task carried over to {tomorrow}",
        "xp_delta": CARRY_OVER_XP,
        "new_total_xp": new_total,
        "new_task_id": new_task_id,
        "scheduled_for": tomorrow,
    }), 200

