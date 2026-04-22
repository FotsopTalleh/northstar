from flask import Blueprint, request, jsonify, g
from app.firebase import get_db
from app.middleware import require_auth
from app.services.xp_service import get_user_xp_logs

user_bp = Blueprint("users", __name__, url_prefix="/api/users")


@user_bp.route("/me", methods=["GET"])
@require_auth
def get_me():
    db = get_db()
    user = db.collection("users").document(g.user_id).get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404
    u = user.to_dict()
    u.pop("password_hash", None)
    u["xp_logs"] = get_user_xp_logs(g.user_id, limit=20)
    return jsonify(u), 200


@user_bp.route("/me", methods=["PATCH"])
@require_auth
def update_me():
    data = request.get_json(silent=True) or {}
    allowed = {}

    if "timezone" in data:
        import pytz
        tz_str = data["timezone"].strip()
        try:
            pytz.timezone(tz_str)
            allowed["timezone"] = tz_str
        except Exception:
            return jsonify({"error": "Invalid timezone string"}), 400

    if "avatar_color" in data:
        color = data["avatar_color"].strip()
        if not color.startswith("#") or len(color) not in (4, 7):
            return jsonify({"error": "avatar_color must be a hex code like #FF5733"}), 400
        allowed["avatar_color"] = color

    if "notifications_enabled" in data:
        val = data["notifications_enabled"]
        if not isinstance(val, bool):
            return jsonify({"error": "notifications_enabled must be true or false"}), 400
        allowed["notifications_enabled"] = val

    if not allowed:
        return jsonify({"error": "No valid fields to update"}), 400

    db = get_db()
    db.collection("users").document(g.user_id).update(allowed)
    return jsonify({"message": "Profile updated", **allowed}), 200


@user_bp.route("/<user_id>", methods=["GET"])
@require_auth
def get_user(user_id):
    db = get_db()
    user = db.collection("users").document(user_id).get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404
    u = user.to_dict()
    return jsonify({
        "user_id": u.get("user_id"),
        "username": u.get("username"),
        "avatar_color": u.get("avatar_color"),
        "total_xp": u.get("total_xp", 0),
        "badges": u.get("badges", []),
        "clan_id": u.get("clan_id"),
        "joined_at": u.get("joined_at"),
    }), 200
