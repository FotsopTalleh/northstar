from flask import Blueprint, jsonify, g
from app.firebase import get_db
from app.middleware import require_auth

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
