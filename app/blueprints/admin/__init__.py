"""
blueprints/admin/__init__.py

Re-exports the `admin_bp` Blueprint object defined in routes.py so it can
be imported cleanly from app/__init__.py as:

    from app.blueprints.admin import admin_bp

Note: the url_prefix="/admin" is applied at REGISTRATION time in
app/__init__.py's create_app() (app.register_blueprint(admin_bp,
url_prefix="/admin")), not on the Blueprint object itself here, so this
package stays consistent with the pattern used by the other HTML
blueprints (auth, dashboard, documents, chat).
"""

from app.blueprints.admin.routes import admin_bp

__all__ = ["admin_bp"]