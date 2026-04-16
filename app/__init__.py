from flask import Flask
from flask_cors import CORS
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from app.firebase import init_firebase

limiter = None

def create_app():
    global limiter
    app = Flask(__name__, static_folder="../frontend", static_url_path="/")
    from app.config import Config
    app.config.from_object(Config)

    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Rate limiter keyed by JWT user_id header when available
    def get_user_key():
        from flask import request, g
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            import jwt
            try:
                payload = jwt.decode(
                    auth.split(" ", 1)[1],
                    Config.SECRET_KEY,
                    algorithms=["HS256"]
                )
                return f"user:{payload['user_id']}"
            except Exception:
                pass
        return get_remote_address()

    limiter = Limiter(
        key_func=get_user_key,
        app=app,
        default_limits=["60 per minute"],
        storage_uri="memory://"
    )

    # Firebase
    init_firebase()

    # Register blueprints
    from app.routes.auth_routes import auth_bp
    from app.routes.plan_routes import plan_bp
    from app.routes.task_routes import task_bp
    from app.routes.leaderboard_routes import leaderboard_bp
    from app.routes.clan_routes import clan_bp
    from app.routes.battle_routes import battle_bp
    from app.routes.notification_routes import notification_bp
    from app.routes.user_routes import user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(plan_bp)
    app.register_blueprint(task_bp)
    app.register_blueprint(leaderboard_bp)
    app.register_blueprint(clan_bp)
    app.register_blueprint(battle_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(user_bp)

    # Serve frontend
    @app.route("/")
    def index():
        return app.send_static_file("index.html")

    @app.route("/<path:path>")
    def static_files(path):
        try:
            return app.send_static_file(path)
        except Exception:
            return app.send_static_file("index.html")

    # Start scheduler
    from app.scheduler import start_scheduler
    start_scheduler(app)

    return app
