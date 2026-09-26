"""
extensions.py

Instantiates all Flask extensions in a single, shared module so they can be
imported without circular-import issues. Extensions are initialized here
(unbound to any app) and then bound to the actual Flask app instance inside
the application factory (app/__init__.py) via each extension's .init_app().

This pattern avoids circular imports between models, blueprints, and the
app factory, since every module imports these extension instances from
this one place instead of importing directly from app/__init__.py.
"""

from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_migrate import Migrate
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS

# ---------------------------------------------------------------------------
# SQLAlchemy — ORM / Database layer (PostgreSQL)
# ---------------------------------------------------------------------------
db = SQLAlchemy()

# ---------------------------------------------------------------------------
# Flask-Migrate — Alembic-based schema migrations
# ---------------------------------------------------------------------------
migrate = Migrate()

# ---------------------------------------------------------------------------
# Flask-Bcrypt — Password hashing
# ---------------------------------------------------------------------------
bcrypt = Bcrypt()

# ---------------------------------------------------------------------------
# Flask-Login — Session-based authentication for students and admins
# ---------------------------------------------------------------------------
login_manager = LoginManager()
login_manager.login_view = "auth.login"
login_manager.login_message = "Please log in to access Minddora AI."
login_manager.login_message_category = "info"
login_manager.session_protection = "strong"

# ---------------------------------------------------------------------------
# Flask-WTF — CSRF protection for all form submissions
# ---------------------------------------------------------------------------
csrf = CSRFProtect()

# ---------------------------------------------------------------------------
# Flask-Limiter — Rate limiting to prevent abuse of auth/upload/chat endpoints
# ---------------------------------------------------------------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"],
)

# ---------------------------------------------------------------------------
# Flask-CORS — Cross-origin support (useful if frontend is later decoupled)
# ---------------------------------------------------------------------------
cors = CORS()