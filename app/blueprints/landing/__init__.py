"""
blueprints/landing/__init__.py

Re-exports the `landing_bp` Blueprint object defined in routes.py so it
can be imported cleanly from app/__init__.py as:

    from app.blueprints.landing import landing_bp

Handles Minddora AI's public-facing marketing pages (Landing, About,
Features, Pricing, Contact) — the only pages accessible without
authentication besides the auth blueprint's Register/Login pages.
"""

from app.blueprints.landing.routes import landing_bp

__all__ = ["landing_bp"]