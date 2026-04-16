import uuid
from datetime import datetime, timezone, timedelta
from flask import Blueprint, request, jsonify
import bcrypt
import jwt
from app.firebase import get_db
from app.config import Config
from app.services.leaderboard_service import update_all_leaderboards

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _generate_jwt(user_id: str, email: str) -> str:
    payload = {
        "user_id": user_id,
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=Config.JWT_EXPIRY_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, Config.SECRET_KEY, algorithm="HS256")


@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")
    username = data.get("username", "").strip()
    timezone_str = data.get("timezone", "UTC").strip()

    # Basic validation
    if not email or not password or not username or not timezone_str:
        return jsonify({"error": "email, password, username, and timezone are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    db = get_db()

    # Check email uniqueness
    existing = db.collection("users").where("email", "==", email).limit(1).get()
    if len(existing) > 0:
        return jsonify({"error": "Email already registered"}), 409

    # Check username uniqueness
    existing_u = db.collection("users").where("username", "==", username).limit(1).get()
    if len(existing_u) > 0:
        return jsonify({"error": "Username already taken"}), 409

    # Hash password
    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    user_doc = {
        "user_id": user_id,
        "email": email,
        "password_hash": pw_hash,
        "username": username,
        "avatar_color": "#6C63FF",
        "timezone": timezone_str,
        "joined_at": now,
        "clan_id": None,
        "total_xp": 0,
        "badges": [],
    }

    db.collection("users").document(user_id).set(user_doc)

    # Initialize leaderboard entry so user appears immediately with 0 XP
    update_all_leaderboards(user_id, 0, username, user_doc["avatar_color"])

    token = _generate_jwt(user_id, email)
    return jsonify({
        "token": token,
        "user": {
            "user_id": user_id,
            "email": email,
            "username": username,
            "avatar_color": user_doc["avatar_color"],
            "timezone": timezone_str,
            "total_xp": 0,
        }
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    password = data.get("password", "")

    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    db = get_db()
    users = db.collection("users").where("email", "==", email).limit(1).get()
    if not users:
        return jsonify({"error": "Invalid credentials"}), 401

    user_data = users[0].to_dict()

    if not bcrypt.checkpw(password.encode(), user_data["password_hash"].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    token = _generate_jwt(user_data["user_id"], email)
    return jsonify({
        "token": token,
        "user": {
            "user_id": user_data["user_id"],
            "email": user_data["email"],
            "username": user_data["username"],
            "avatar_color": user_data.get("avatar_color", "#6C63FF"),
            "timezone": user_data.get("timezone", "UTC"),
            "total_xp": user_data.get("total_xp", 0),
            "clan_id": user_data.get("clan_id"),
        }
    }), 200
