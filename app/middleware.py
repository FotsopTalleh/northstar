from functools import wraps
import jwt
from flask import request, jsonify, g
from app.config import Config

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid authorization header"}), 401
        token = auth_header.split(" ", 1)[1]
        try:
            payload = jwt.decode(token, Config.SECRET_KEY, algorithms=["HS256"])
            g.user_id = payload["user_id"]
            g.email = payload.get("email", "")
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Token expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated
