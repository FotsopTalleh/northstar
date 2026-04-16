import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify, g
from app.firebase import get_db
from app.middleware import require_auth
from app.services.notification_service import notify_battle_challenge, notify_clan_falling_behind
from app.services.badge_service import assign_warchief_badge

battle_bp = Blueprint("battles", __name__, url_prefix="/api/battles")

MIN_MEMBERS = 5


def _get_user_clan(db, user_id: str):
    user = db.collection("users").document(user_id).get()
    if not user.exists:
        return None, None
    clan_id = user.to_dict().get("clan_id")
    if not clan_id:
        return None, None
    clan = db.collection("clans").document(clan_id).get()
    return clan_id, clan.to_dict() if clan.exists else None


def _has_active_battle(db, clan_id: str) -> bool:
    battles = (
        db.collection("clan_battles")
        .where("clan_a_id", "==", clan_id)
        .where("status", "==", "active")
        .limit(1)
        .get()
    )
    if battles:
        return True
    battles = (
        db.collection("clan_battles")
        .where("clan_b_id", "==", clan_id)
        .where("status", "==", "active")
        .limit(1)
        .get()
    )
    return bool(battles)


@battle_bp.route("/challenge", methods=["POST"])
@require_auth
def challenge():
    data = request.get_json(silent=True) or {}
    target_clan_id = data.get("target_clan_id", "").strip()
    duration = data.get("duration", "1d")  # "1d" or "1w"

    if duration not in ("1d", "1w"):
        return jsonify({"error": "duration must be '1d' or '1w'"}), 400
    if not target_clan_id:
        return jsonify({"error": "target_clan_id is required"}), 400

    db = get_db()
    my_clan_id, my_clan = _get_user_clan(db, g.user_id)

    if not my_clan:
        return jsonify({"error": "You are not in a clan"}), 400
    if my_clan["leader_id"] != g.user_id:
        return jsonify({"error": "Only the clan leader can initiate battles"}), 403
    if len(my_clan.get("member_ids", [])) < MIN_MEMBERS:
        return jsonify({"error": "Your clan needs at least 5 members to battle"}), 400
    if _has_active_battle(db, my_clan_id):
        return jsonify({"error": "Your clan already has an active battle"}), 409

    target_clan = db.collection("clans").document(target_clan_id).get()
    if not target_clan.exists:
        return jsonify({"error": "Target clan not found"}), 404
    target_data = target_clan.to_dict()

    if len(target_data.get("member_ids", [])) < MIN_MEMBERS:
        return jsonify({"error": "Target clan needs at least 5 members"}), 400
    if _has_active_battle(db, target_clan_id):
        return jsonify({"error": "Target clan already has an active battle"}), 409

    battle_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    end_at = now + (timedelta(days=1) if duration == "1d" else timedelta(weeks=1))

    battle_doc = {
        "battle_id": battle_id,
        "clan_a_id": my_clan_id,
        "clan_b_id": target_clan_id,
        "initiated_by": g.user_id,
        "accepted_by": None,
        "duration": duration,
        "start_at": now.isoformat(),
        "end_at": end_at.isoformat(),
        "status": "pending",
        "winner_clan_id": None,
        "avg_xp_a": 0,
        "avg_xp_b": 0,
    }
    db.collection("clan_battles").document(battle_id).set(battle_doc)

    # Notify target clan leader
    notify_battle_challenge(target_data["leader_id"], my_clan["name"])

    return jsonify(battle_doc), 201


@battle_bp.route("/accept", methods=["POST"])
@require_auth
def accept():
    data = request.get_json(silent=True) or {}
    battle_id = data.get("battle_id", "").strip()
    if not battle_id:
        return jsonify({"error": "battle_id is required"}), 400

    db = get_db()
    battle_ref = db.collection("clan_battles").document(battle_id)
    battle = battle_ref.get()
    if not battle.exists:
        return jsonify({"error": "Battle not found"}), 404
    battle_data = battle.to_dict()

    if battle_data["status"] != "pending":
        return jsonify({"error": "Battle is not pending"}), 409

    my_clan_id, my_clan = _get_user_clan(db, g.user_id)
    if not my_clan or my_clan_id != battle_data["clan_b_id"]:
        return jsonify({"error": "You are not the leader of the challenged clan"}), 403
    if my_clan["leader_id"] != g.user_id:
        return jsonify({"error": "Only the clan leader can accept battles"}), 403

    battle_ref.update({"status": "active", "accepted_by": g.user_id})
    return jsonify({"message": "Battle accepted", "battle_id": battle_id}), 200


@battle_bp.route("/<battle_id>", methods=["GET"])
@require_auth
def get_battle(battle_id):
    db = get_db()
    battle = db.collection("clan_battles").document(battle_id).get()
    if not battle.exists:
        return jsonify({"error": "Battle not found"}), 404

    battle_data = battle.to_dict()

    def clan_summary(clan_id):
        clan = db.collection("clans").document(clan_id).get()
        if not clan.exists:
            return {}
        cd = clan.to_dict()
        members = cd.get("member_ids", [])
        total_xp = sum(
            db.collection("users").document(uid).get().to_dict().get("total_xp", 0)
            for uid in members
        )
        avg_xp = total_xp / len(members) if members else 0
        return {"clan_id": clan_id, "name": cd.get("name"), "member_count": len(members), "avg_xp": round(avg_xp, 2)}

    return jsonify({
        **battle_data,
        "clan_a": clan_summary(battle_data["clan_a_id"]),
        "clan_b": clan_summary(battle_data["clan_b_id"]),
    }), 200
