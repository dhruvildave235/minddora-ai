"""
__init__.py (Application Factory)

This module defines create_app(), the Flask application factory for Minddora AI.

Responsibilities:
    1. Instantiate the Flask app.
    2. Load configuration based on the FLASK_ENV environment variable.
    3. Bind all shared extensions (SQLAlchemy/PostgreSQL, Login, Bcrypt, etc.)
       from extensions.py to this app instance.
    4. Register all blueprints (auth, dashboard, documents, chat, admin, api).
    5. Register global error handlers (404, 500).
    6. Configure application-wide logging.
    7. Ensure required storage directories exist on startup.

Using the factory pattern (rather than a global app object) avoids circular
imports and allows multiple app instances to be created cleanly for testing.
"""

import os

# from flask import Flask, render_template
from flask import Flask, render_template, request, jsonify

from app.config import config_by_name
from app.extensions import db, migrate, bcrypt, login_manager, csrf, limiter, cors
from app.utils.logger import configure_logging
from werkzeug.middleware.proxy_fix import ProxyFix
from app.blueprints.api.rag_viz_api import rag_viz_api_bp

def create_app(config_name: str = None) -> Flask:
    """
    Application factory function.

    Args:
        config_name (str, optional): One of "development", "testing", "production".
            If not provided, falls back to the FLASK_ENV environment variable,
            defaulting to "development".

    Returns:
        Flask: A fully configured Flask application instance.
    """

    # -----------------------------------------------------------------
    # 1. Determine and load configuration
    # -----------------------------------------------------------------
    config_name = config_name or os.environ.get("FLASK_ENV", "development")

    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
        instance_relative_config=True,
    )
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    @app.before_request
    def set_dynamic_cookie_security():
        from flask import request
        app.config["SESSION_COOKIE_SECURE"] = request.is_secure
    app.config.from_object(config_by_name[config_name])

    # -----------------------------------------------------------------
    # 2. Ensure required storage directories exist
    #    (uploads, vector_db, logs) — created relative to project root
    #    as defined in config.py, since PostgreSQL handles all
    #    structured data but files/vectors/logs live on disk.
    # -----------------------------------------------------------------
    for folder_key in ("UPLOAD_FOLDER", "VECTOR_DB_PATH", "LOG_FOLDER"):
        folder_path = app.config.get(folder_key)
        if folder_path:
            os.makedirs(folder_path, exist_ok=True)

    # -----------------------------------------------------------------
    # 3. Initialize extensions with this app instance
    # -----------------------------------------------------------------
    db.init_app(app)                # PostgreSQL connection via SQLAlchemy
    migrate.init_app(app, db)       # Alembic migrations against PostgreSQL
    bcrypt.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    cors.init_app(app)

    # -----------------------------------------------------------------
    # 4. Configure centralized logging
    # -----------------------------------------------------------------
    configure_logging(app)

    # -----------------------------------------------------------------
    # 5. Register the user loader for Flask-Login
    #    (imported here, lazily, to avoid circular imports with models)
    # -----------------------------------------------------------------
    from app.models.user import User
    from app.models.admin import Admin

    @login_manager.user_loader
    def load_user(user_id: str):
        """
        Flask-Login callback used to reload a user object from the user ID
        stored in the session. Checks the Student (User) table first, then
        falls back to the Admin table, since both roles authenticate
        through the same session mechanism but live in separate tables.
        """
        if user_id.startswith("admin-"):
            return Admin.query.get(int(user_id.replace("admin-", "")))
        return User.query.get(int(user_id))

    # -----------------------------------------------------------------
    # 5b. Local edition: auto-provision and auto-login a single local
    #     profile on every request. There is no login system in this
    #     open-source local edition — the app is meant to run on your
    #     own machine, so there is nothing to protect from yourself.
    #     Every existing per-user query (documents, chunks, chats,
    #     feedback) keeps working completely unchanged, since they all
    #     still key off current_user.id — it's just always the same
    #     one profile now, created automatically the first time the
    #     app runs.
    # -----------------------------------------------------------------
    LOCAL_PROFILE_EMAIL = "local@minddora.app"

    @app.before_request
    def auto_login_local_profile():
        from flask_login import current_user, login_user

        if current_user.is_authenticated:
            return
        if request.path.startswith("/static/"):
            return

        local_user = User.query.filter_by(email=LOCAL_PROFILE_EMAIL).first()
        if local_user is None:
            local_user = User(
                full_name="Local User",
                email=LOCAL_PROFILE_EMAIL,
                password_hash="",  # No login system — this field is unused in the local edition
                is_email_verified=True,
                is_active=True,
            )
            db.session.add(local_user)
            db.session.commit()

        login_user(local_user, remember=True)

    # -----------------------------------------------------------------
    # 6. Register blueprints
    # -----------------------------------------------------------------
    from app.blueprints.landing import landing_bp
    from app.blueprints.auth import auth_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.documents import documents_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.api.auth_api import auth_api_bp
    from app.blueprints.api.document_api import document_api_bp
    from app.blueprints.api.chat_api import chat_api_bp
    from app.blueprints.api.search_api import search_api_bp
    from app.blueprints.api.admin_api import admin_api_bp
    from app.blueprints.api.feedback_api import feedback_api_bp
    from app.blueprints.api.database_api import database_api_bp

    app.register_blueprint(landing_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(admin_bp, url_prefix="/admin")

    app.register_blueprint(auth_api_bp, url_prefix="/api/auth")
    app.register_blueprint(document_api_bp, url_prefix="/api/documents")
    app.register_blueprint(chat_api_bp, url_prefix="/api/chat")
    app.register_blueprint(search_api_bp, url_prefix="/api/search")
    app.register_blueprint(admin_api_bp, url_prefix="/api/admin")
    app.register_blueprint(feedback_api_bp, url_prefix="/api/feedback")
    app.register_blueprint(database_api_bp, url_prefix="/api/admin/database")

    app.register_blueprint(rag_viz_api_bp, url_prefix="/api/admin/rag-viz")


    # -----------------------------------------------------------------
    # 7. Global error handlers
    # -----------------------------------------------------------------
    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()  # Roll back any broken PostgreSQL transaction
        app.logger.error(f"Internal server error: {error}")
        return render_template("errors/500.html"), 500

    @app.errorhandler(429)
    def rate_limit_error(error):
        if request.path.startswith("/api/"):
            return jsonify({
                "success": False,
                "error": "Too many requests. Please wait a moment and try again.",
                "error_code": "RATE_LIMITED",
            }), 429
        return render_template("errors/429.html"), 429  
   

    # -----------------------------------------------------------------
    # Prevent browser/proxy caching of API responses, so status changes
    # (e.g. admin suspending/reactivating a user) are always reflected
    # immediately on the next request, never served from a stale cache.
    # -----------------------------------------------------------------
    @app.after_request
    def add_no_cache_headers(response):
        if request.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        return response


    @app.before_request
    def update_last_seen():
        from flask_login import current_user
        from app.models.user import User

        if current_user.is_authenticated and isinstance(current_user, User):
            from datetime import datetime, timezone
            current_user.last_seen_at = datetime.now(timezone.utc)
            db.session.commit()

    # -----------------------------------------------------------------
    # 8. Shell context for `flask shell` (useful for debugging PostgreSQL data)
    # -----------------------------------------------------------------
    @app.shell_context_processor
    def make_shell_context():
        from app.models.document import Document
        from app.models.chunk import Chunk
        from app.models.chat import ChatSession, ChatMessage

        return {
            "db": db,
            "User": User,
            "Admin": Admin,
            "Document": Document,
            "Chunk": Chunk,
            "ChatSession": ChatSession,
            "ChatMessage": ChatMessage,
        }

    return app