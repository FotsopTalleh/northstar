from flask import Blueprint, request, jsonify, g
from app.middleware import require_auth
from app.services.clan_service import (
    create_clan, invite_user, join_clan, leave_clan,
    transfer_leadership, get_clan_profile, respond_to_invite, kick_member
)

clan_bp = Blueprint("clans", __name__, url_prefix="/api/clans")


@clan_bp.route("/create", methods=["POST"])
@require_auth
def create():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    description = data.get("description", "").strip()
    if not name:
        return jsonify({"error": "Clan name is required"}), 400
    try:
        clan = create_clan(g.user_id, name, description)
        return jsonify(clan), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/invite", methods=["POST"])
@require_auth
def invite():
    data = request.get_json(silent=True) or {}
    clan_id = data.get("clan_id", "").strip()
    invitee_id = data.get("user_id", "").strip()
    if not clan_id or not invitee_id:
        return jsonify({"error": "clan_id and user_id are required"}), 400
    try:
        result = invite_user(clan_id, g.user_id, invitee_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/join", methods=["POST"])
@require_auth
def join():
    data = request.get_json(silent=True) or {}
    clan_id = data.get("clan_id", "").strip()
    if not clan_id:
        return jsonify({"error": "clan_id is required"}), 400
    try:
        result = join_clan(g.user_id, clan_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/respond-invite", methods=["POST"])
@require_auth
def respond_invite():
    data = request.get_json(silent=True) or {}
    notif_id = data.get("notification_id", "").strip()
    action = data.get("action", "").strip()
    if not notif_id or not action:
        return jsonify({"error": "notification_id and action required"}), 400
    try:
        result = respond_to_invite(g.user_id, notif_id, action)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/leave", methods=["POST"])
@require_auth
def leave():
    from app.firebase import get_db
    db = get_db()
    user = db.collection("users").document(g.user_id).get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404
    clan_id = user.to_dict().get("clan_id")
    if not clan_id:
        return jsonify({"error": "You are not in a clan"}), 400
    try:
        result = leave_clan(g.user_id, clan_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/kick", methods=["POST"])
@require_auth
def kick():
    data = request.get_json(silent=True) or {}
    target_id = data.get("user_id", "").strip()
    if not target_id:
        return jsonify({"error": "user_id is required"}), 400
    from app.firebase import get_db
    db = get_db()
    user = db.collection("users").document(g.user_id).get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404
    clan_id = user.to_dict().get("clan_id")
    if not clan_id:
        return jsonify({"error": "You are not in a clan"}), 400
    try:
        result = kick_member(g.user_id, clan_id, target_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/transfer-leadership", methods=["POST"])
@require_auth
def transfer():
    data = request.get_json(silent=True) or {}
    new_leader_id = data.get("new_leader_id", "").strip()
    if not new_leader_id:
        return jsonify({"error": "new_leader_id is required"}), 400
    from app.firebase import get_db
    db = get_db()
    user = db.collection("users").document(g.user_id).get()
    if not user.exists:
        return jsonify({"error": "User not found"}), 404
    clan_id = user.to_dict().get("clan_id")
    if not clan_id:
        return jsonify({"error": "You are not in a clan"}), 400
    try:
        result = transfer_leadership(clan_id, g.user_id, new_leader_id)
        return jsonify(result), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@clan_bp.route("/<clan_id>", methods=["GET"])
@require_auth
def clan_profile(clan_id):
    try:
        profile = get_clan_profile(clan_id)
        return jsonify(profile), 200
    except ValueError as e:
        return jsonify({"error": str(e)}), 404
