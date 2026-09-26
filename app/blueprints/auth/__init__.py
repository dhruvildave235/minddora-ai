"""
blueprints/auth/__init__.py

Re-exports the `auth_bp` Blueprint object defined in routes.py so it can
be imported cleanly from app/__init__.py as:

    from app.blueprints.auth import auth_bp

The Blueprint itself (including its url_prefix="/auth") is instantiated
in routes.py, not here — this file exists purely as the package's public
import surface, keeping the registration line in the application factory
short and consistent with the other blueprint packages
(dashboard, documents, chat, admin, api).
"""

from app.blueprints.auth.routes import auth_bp

__all__ = ["auth_bp"]