import uuid
import smtplib
import urllib.request
import urllib.parse
import json as _json
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
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


def _send_reset_email(to_email: str, reset_token: str):
    """Send a password reset email via Gmail SMTP."""
    reset_url = f"{Config.APP_URL}/reset-password.html?token={reset_token}"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "XPForge — Reset your password"
    msg["From"]    = Config.SMTP_EMAIL
    msg["To"]      = to_email

    html = f"""
    <div style="font-family:'Inter',sans-serif;max-width:480px;margin:0 auto;padding:32px 24px;
                background:#0a0b0f;color:#f0f2ff;border-radius:16px">
      <h1 style="font-size:1.6rem;font-weight:800;margin-bottom:8px;
                 background:linear-gradient(135deg,#8b84ff,#f5c518);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent">
        ⚡ XPForge
      </h1>
      <p style="color:#9aa3c0;margin-bottom:24px">Someone requested a password reset for your account.</p>
      <a href="{reset_url}"
         style="display:inline-block;background:linear-gradient(135deg,#6c63ff,#9b5de5);
                color:#fff;font-weight:700;padding:14px 28px;border-radius:10px;
                text-decoration:none;font-size:1rem">
        Reset My Password
      </a>
      <p style="color:#5a6180;font-size:.82rem;margin-top:24px">
        This link expires in <strong>1 hour</strong>. If you didn't request this, ignore this email.
      </p>
      <hr style="border-color:#2a2f3e;margin:24px 0">
      <p style="color:#5a6180;font-size:.75rem">XPForge Accountability System</p>
    </div>
    """
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(Config.SMTP_EMAIL, Config.SMTP_PASSWORD)
        server.sendmail(Config.SMTP_EMAIL, to_email, msg.as_string())


# ─── SIGNUP ─────────────────────────────────────────────────────────────────
@auth_bp.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True) or {}
    email        = data.get("email", "").strip().lower()
    password     = data.get("password", "")
    username     = data.get("username", "").strip()
    timezone_str = data.get("timezone", "UTC").strip()

    if not email or not password or not username or not timezone_str:
        return jsonify({"error": "email, password, username, and timezone are required"}), 400
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    db = get_db()

    existing = db.collection("users").where("email", "==", email).limit(1).get()
    if len(existing) > 0:
        return jsonify({"error": "Email already registered"}), 409

    existing_u = db.collection("users").where("username", "==", username).limit(1).get()
    if len(existing_u) > 0:
        return jsonify({"error": "Username already taken"}), 409

    pw_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    user_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    user_doc = {
        "user_id":       user_id,
        "email":         email,
        "password_hash": pw_hash,
        "username":      username,
        "avatar_color":  "#6C63FF",
        "timezone":      timezone_str,
        "joined_at":     now,
        "clan_id":       None,
        "total_xp":      0,
        "badges":        [],
    }
    db.collection("users").document(user_id).set(user_doc)
    update_all_leaderboards(user_id, 0, username, user_doc["avatar_color"])

    token = _generate_jwt(user_id, email)
    return jsonify({
        "token": token,
        "user": {
            "user_id":      user_id,
            "email":        email,
            "username":     username,
            "avatar_color": user_doc["avatar_color"],
            "timezone":     timezone_str,
            "total_xp":     0,
        }
    }), 201


# ─── LOGIN ───────────────────────────────────────────────────────────────────
@auth_bp.route("/login", methods=["POST"])
def login():
    data       = request.get_json(silent=True) or {}
    # Accept `identifier` (email or username) or legacy `email` field
    identifier = (data.get("identifier") or data.get("email") or "").strip()
    password   = data.get("password", "")

    if not identifier or not password:
        return jsonify({"error": "Email/username and password are required"}), 400

    db = get_db()

    # Detect whether the user typed an email or a username
    if "@" in identifier:
        users = db.collection("users").where("email", "==", identifier.lower()).limit(1).get()
    else:
        users = db.collection("users").where("username", "==", identifier).limit(1).get()

    if not users:
        return jsonify({"error": "Invalid credentials"}), 401

    user_data = users[0].to_dict()

    if not user_data.get("password_hash"):
        return jsonify({"error": "This account uses Google Sign-In. Please sign in with Google."}), 400

    if not bcrypt.checkpw(password.encode(), user_data["password_hash"].encode()):
        return jsonify({"error": "Invalid credentials"}), 401

    token = _generate_jwt(user_data["user_id"], user_data["email"])
    return jsonify({
        "token": token,
        "user": {
            "user_id":      user_data["user_id"],
            "email":        user_data["email"],
            "username":     user_data["username"],
            "avatar_color": user_data.get("avatar_color", "#6C63FF"),
            "timezone":     user_data.get("timezone", "UTC"),
            "total_xp":     user_data.get("total_xp", 0),
            "clan_id":      user_data.get("clan_id"),
        }
    }), 200


# ─── FORGOT PASSWORD ─────────────────────────────────────────────────────────
@auth_bp.route("/forgot-password", methods=["POST"])
def forgot_password():
    data  = request.get_json(silent=True) or {}
    email = data.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "email is required"}), 400

    db = get_db()
    users = db.collection("users").where("email", "==", email).limit(1).get()
    # Always return 200 to prevent email enumeration
    if not users:
        return jsonify({"message": "If that email is registered, a reset link has been sent."}), 200

    user_data = users[0].to_dict()
    if not user_data.get("password_hash"):
        return jsonify({"message": "If that email is registered, a reset link has been sent."}), 200

    reset_token = str(uuid.uuid4())
    expires_at  = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()

    db.collection("password_resets").document(reset_token).set({
        "token":      reset_token,
        "user_id":    user_data["user_id"],
        "email":      email,
        "expires_at": expires_at,
        "used":       False,
    })

    try:
        _send_reset_email(email, reset_token)
    except Exception as e:
        return jsonify({"error": f"Failed to send email: {str(e)}"}), 500

    return jsonify({"message": "If that email is registered, a reset link has been sent."}), 200


# ─── RESET PASSWORD ──────────────────────────────────────────────────────────
@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data         = request.get_json(silent=True) or {}
    token        = data.get("token", "").strip()
    new_password = data.get("password", "")

    if not token or not new_password:
        return jsonify({"error": "token and password are required"}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Password must be at least 6 characters"}), 400

    db = get_db()
    reset_ref = db.collection("password_resets").document(token)
    reset_doc = reset_ref.get()

    if not reset_doc.exists:
        return jsonify({"error": "Invalid or expired reset link"}), 400

    reset_data = reset_doc.to_dict()
    if reset_data.get("used"):
        return jsonify({"error": "This reset link has already been used"}), 400

    expires_at = datetime.fromisoformat(reset_data["expires_at"])
    if datetime.now(timezone.utc) > expires_at:
        return jsonify({"error": "This reset link has expired"}), 400

    new_hash = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
    user_id  = reset_data["user_id"]

    db.collection("users").document(user_id).update({"password_hash": new_hash})
    reset_ref.update({"used": True})

    # Auto-login: return a fresh JWT
    user = db.collection("users").document(user_id).get().to_dict()
    token_jwt = _generate_jwt(user_id, user["email"])
    return jsonify({
        "message": "Password reset successfully!",
        "token": token_jwt,
        "user": {
            "user_id":      user["user_id"],
            "email":        user["email"],
            "username":     user["username"],
            "avatar_color": user.get("avatar_color", "#6C63FF"),
            "timezone":     user.get("timezone", "UTC"),
            "total_xp":     user.get("total_xp", 0),
            "clan_id":      user.get("clan_id"),
        }
    }), 200


# ─── GOOGLE SIGN-IN ──────────────────────────────────────────────────────────
@auth_bp.route("/google", methods=["POST"])
def google_signin():
    """Verify a Google ID token and return an app JWT."""
    data     = request.get_json(silent=True) or {}
    id_token = data.get("credential", "").strip()
    if not id_token:
        return jsonify({"error": "Google credential is required"}), 400

    # Verify token with Google's tokeninfo endpoint
    try:
        url      = f"https://oauth2.googleapis.com/tokeninfo?id_token={urllib.parse.quote(id_token)}"
        with urllib.request.urlopen(url, timeout=5) as resp:
            payload = _json.loads(resp.read().decode())
    except Exception:
        return jsonify({"error": "Invalid Google token"}), 401

    # Verify audience
    if payload.get("aud") != Config.GOOGLE_CLIENT_ID:
        return jsonify({"error": "Token audience mismatch"}), 401

    email    = payload.get("email", "").lower()
    name     = payload.get("name") or payload.get("given_name") or email.split("@")[0]
    if not email:
        return jsonify({"error": "Could not read email from Google token"}), 400

    db = get_db()
    users = db.collection("users").where("email", "==", email).limit(1).get()

    if users:
        # Existing user — return JWT
        user_data = users[0].to_dict()
    else:
        # New user — create account (no password_hash)
        user_id  = str(uuid.uuid4())
        username = name.replace(" ", "").lower()[:20]
        # Ensure username is unique
        base = username
        counter = 1
        while db.collection("users").where("username", "==", username).limit(1).get():
            username = f"{base}{counter}"
            counter += 1

        now = datetime.now(timezone.utc).isoformat()
        user_data = {
            "user_id":       user_id,
            "email":         email,
            "password_hash": None,   # Google users have no password
            "username":      username,
            "avatar_color":  "#6C63FF",
            "timezone":      "UTC",
            "joined_at":     now,
            "clan_id":       None,
            "total_xp":      0,
            "badges":        [],
            "auth_provider": "google",
        }
        db.collection("users").document(user_id).set(user_data)
        update_all_leaderboards(user_id, 0, username, user_data["avatar_color"])

    token = _generate_jwt(user_data["user_id"], email)
    return jsonify({
        "token": token,
        "user": {
            "user_id":      user_data["user_id"],
            "email":        user_data["email"],
            "username":     user_data["username"],
            "avatar_color": user_data.get("avatar_color", "#6C63FF"),
            "timezone":     user_data.get("timezone", "UTC"),
            "total_xp":     user_data.get("total_xp",  0),
            "clan_id":      user_data.get("clan_id"),
        }
    }), 200
