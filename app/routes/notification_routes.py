from flask import Blueprint, jsonify, g, request
from app.firebase import get_db
from app.middleware import require_auth
from app.services.notification_service import create_notification

notification_bp = Blueprint("notifications", __name__, url_prefix="/api/notifications")


@notification_bp.route("", methods=["GET"])
@require_auth
def get_notifications():
    db = get_db()
    docs = (
        db.collection("notifications")
        .where("user_id", "==", g.user_id)
        .get()
    )
    notifs = [d.to_dict() for d in docs]
    notifs.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return jsonify(notifs[:50]), 200


@notification_bp.route("/<notif_id>/read", methods=["PATCH"])
@require_auth
def mark_read(notif_id):
    db = get_db()
    ref = db.collection("notifications").document(notif_id)
    doc = ref.get()
    if not doc.exists:
        return jsonify({"error": "Notification not found"}), 404
    if doc.to_dict().get("user_id") != g.user_id:
        return jsonify({"error": "Forbidden"}), 403
    ref.update({"read": True})
    return jsonify({"message": "Marked as read"}), 200


@notification_bp.route("/read-all", methods=["PATCH"])
@require_auth
def mark_all_read():
    db = get_db()
    docs = (
        db.collection("notifications")
        .where("user_id", "==", g.user_id)
        .where("read", "==", False)
        .get()
    )
    batch = db.batch()
    for doc in docs:
        batch.update(doc.reference, {"read": True})
    batch.commit()
    return jsonify({"message": f"Marked {len(docs)} notifications as read"}), 200


# ── TEST ENDPOINT ─────────────────────────────────────────────────────────────
_TEST_MESSAGES = {
    "no_tasks_reminder":      "Morning check-in: You haven't planned your tasks for today yet. Lock in your goals now!",
    "plan_not_locked":        "You have tasks but your plan is not locked yet. Lock it in to commit to your day!",
    "tasks_pending_reminder": "You still have 3 pending tasks for today. Don't let the day slip away!",
    "clan_losing":            "Your clan is losing the battle vs Rival Clan! They lead by 12.5 avg XP. Complete your tasks to catch up!",
    "overtaken":              "SomePlayer just passed you on the daily leaderboard!",
    "reached_top":            "You are now #1 on the daily leaderboard! You are the beast — keep the lead!",
    "battle_challenge":       "WarClan has challenged your clan to a battle! (1d)",
    "daily_summary":          "Day complete! XP: +42 | Rank: #3",
    "peer_activity":          "BeastMode99 completed 5 tasks today.",
}


@notification_bp.route("/test", methods=["POST"])
@require_auth
def send_test_notification():
    data = request.get_json(silent=True) or {}
    notif_type = data.get("type", "").strip()

    if notif_type not in _TEST_MESSAGES:
        return jsonify({
            "error": f"Unknown type. Valid types: {list(_TEST_MESSAGES.keys())}"
        }), 400

    notif_id = create_notification(
        g.user_id,
        notif_type,
        _TEST_MESSAGES[notif_type],
    )
    return jsonify({"message": "Test notification sent", "notification_id": notif_id}), 201
