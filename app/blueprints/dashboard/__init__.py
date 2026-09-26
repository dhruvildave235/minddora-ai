"""
blueprints/dashboard/__init__.py

Re-exports the `dashboard_bp` Blueprint object defined in routes.py so it
can be imported cleanly from app/__init__.py as:

    from app.blueprints.dashboard import dashboard_bp

The Blueprint itself is instantiated in routes.py; this file exists
purely as the package's public import surface.
"""

from app.blueprints.dashboard.routes import dashboard_bp

__all__ = ["dashboard_bp"]