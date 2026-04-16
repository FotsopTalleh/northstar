from flask import Blueprint, jsonify
from app.middleware import require_auth
from app.services.leaderboard_service import get_leaderboard, get_clan_leaderboard

leaderboard_bp = Blueprint("leaderboard", __name__, url_prefix="/api/leaderboard")


@leaderboard_bp.route("/daily", methods=["GET"])
@require_auth
def daily():
    return jsonify(get_leaderboard("daily")), 200


@leaderboard_bp.route("/weekly", methods=["GET"])
@require_auth
def weekly():
    return jsonify(get_leaderboard("weekly")), 200


@leaderboard_bp.route("/monthly", methods=["GET"])
@require_auth
def monthly():
    return jsonify(get_leaderboard("monthly")), 200


@leaderboard_bp.route("/yearly", methods=["GET"])
@require_auth
def yearly():
    return jsonify(get_leaderboard("yearly")), 200


@leaderboard_bp.route("/global", methods=["GET"])
@require_auth
def global_lb():
    return jsonify(get_leaderboard("global")), 200


@leaderboard_bp.route("/clan/<clan_id>", methods=["GET"])
@require_auth
def clan_lb(clan_id):
    return jsonify(get_clan_leaderboard(clan_id)), 200
