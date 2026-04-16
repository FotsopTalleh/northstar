import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
import pytz
from app.firebase import get_db
from app.middleware import require_auth
from app.services.xp_service import award_provisional_xp, deduct_provisional_xp

task_bp = Blueprint("tasks", __name__, url_prefix="/api/tasks")

MAX_PLANNED = 10
MAX_UNPLANNED = 5


def _get_today_for_user(tz_str: str) -> str:
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.utc
    return datetime.now(tz).strftime("%Y-%m-%d")


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
