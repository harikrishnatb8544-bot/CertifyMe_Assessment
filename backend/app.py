from flask import Flask, jsonify, send_from_directory
from datetime import timedelta

from .auth import auth_bp
from .db import close_db, init_app as init_db_app
from .opportunities import opportunities_bp


def create_app(test_config=None):
    app = Flask(__name__, static_folder="../sky", static_url_path="")
    app.config.from_mapping(
        DATABASE_PATH="instance/admin_portal.db",
        JSON_SORT_KEYS=False,
        MAX_CONTENT_LENGTH=1024 * 1024,
        SECRET_KEY="dev-secret-key-change-me",
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        RESET_TOKEN_LIFETIME=timedelta(hours=1),
        RESET_LINK_LOG_PATH="instance/password_reset_links.log",
        OPPORTUNITY_LOG_PATH="instance/opportunity_logs.log",
    )

    if test_config:
        app.config.update(test_config)

    init_db_app(app)
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(opportunities_bp, url_prefix="/api/opportunities")
    app.teardown_appcontext(close_db)

    @app.get("/")
    def index():
        return send_from_directory(app.static_folder, "admin.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    return app
