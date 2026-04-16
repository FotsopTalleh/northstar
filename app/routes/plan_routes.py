import uuid
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, g
import pytz
from app.firebase import get_db
from app.middleware import require_auth

plan_bp = Blueprint("plans", __name__, url_prefix="/api/plans")


def _get_today_for_user(tz_str: str) -> str:
    """Return today's date string YYYY-MM-DD in the user's timezone."""
    try:
        tz = pytz.timezone(tz_str)
    except Exception:
        tz = pytz.utc
    return datetime.now(tz).strftime("%Y-%m-%d")


def _get_or_create_plan(db, user_id: str, date: str):
    """Return (plan_id, plan_data). Creates the plan document if it doesn't exist."""
    plans = (
        db.collection("daily_plans")
        .where("user_id", "==", user_id)
        .where("date", "==", date)
        .limit(1)
        .get()
    )
    if plans:
        doc = plans[0]
        return doc.id, doc.to_dict()

    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    plan_data = {
        "user_id": user_id,
        "date": date,
        "locked": False,
        "locked_at": None,
        "created_at": now,
    }
    db.collection("daily_plans").document(plan_id).set(plan_data)
    return plan_id, plan_data


@plan_bp.route("/create", methods=["POST"])
@require_auth
def create_plan():
    db = get_db()
    user_ref = db.collection("users").document(g.user_id)
    user = user_ref.get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404

    tz_str = user.to_dict().get("timezone", "UTC")
    date = _get_today_for_user(tz_str)
    plan_id, plan_data = _get_or_create_plan(db, g.user_id, date)
    plan_data["plan_id"] = plan_id
    return jsonify(plan_data), 200


@plan_bp.route("/lock", methods=["POST"])
@require_auth
def lock_plan():
    db = get_db()
    user_ref = db.collection("users").document(g.user_id)
    user = user_ref.get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404

    tz_str = user.to_dict().get("timezone", "UTC")
    date = _get_today_for_user(tz_str)

    plans = (
        db.collection("daily_plans")
        .where("user_id", "==", g.user_id)
        .where("date", "==", date)
        .limit(1)
        .get()
    )
    if not plans:
        return jsonify({"error": "No plan for today. Create one first."}), 404

    plan_doc = plans[0]
    plan_data = plan_doc.to_dict()

    if plan_data.get("locked"):
        return jsonify({"error": "Plan is already locked"}), 409

    # Must have at least one planned task before locking
    tasks = (
        db.collection("tasks")
        .where("plan_id", "==", plan_doc.id)
        .where("type", "==", "planned")
        .limit(1)
        .get()
    )
    if not tasks:
        return jsonify({"error": "Add at least one planned task before locking"}), 400

    now = datetime.now(timezone.utc).isoformat()
    plan_doc.reference.update({"locked": True, "locked_at": now})
    return jsonify({"message": "Plan locked", "locked_at": now}), 200


@plan_bp.route("/today", methods=["GET"])
@require_auth
def today_plan():
    db = get_db()
    user_ref = db.collection("users").document(g.user_id)
    user = user_ref.get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404

    tz_str = user.to_dict().get("timezone", "UTC")
    date = _get_today_for_user(tz_str)

    plans = (
        db.collection("daily_plans")
        .where("user_id", "==", g.user_id)
        .where("date", "==", date)
        .limit(1)
        .get()
    )

    if not plans:
        return jsonify({"plan": None, "tasks": [], "date": date}), 200

    plan_doc = plans[0]
    plan_data = plan_doc.to_dict()
    plan_data["plan_id"] = plan_doc.id

    # Fetch tasks
    task_docs = (
        db.collection("tasks")
        .where("user_id", "==", g.user_id)
        .where("date", "==", date)
        .get()
    )
    tasks = []
    for t in task_docs:
        td = t.to_dict()
        td["task_id"] = t.id
        tasks.append(td)

    return jsonify({"plan": plan_data, "tasks": tasks, "date": date}), 200
