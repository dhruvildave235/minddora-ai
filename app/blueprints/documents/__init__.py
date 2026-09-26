"""
blueprints/documents/__init__.py

Re-exports the `documents_bp` Blueprint object defined in routes.py so it
can be imported cleanly from app/__init__.py as:

    from app.blueprints.documents import documents_bp

The Blueprint itself is instantiated in routes.py; this file exists
purely as the package's public import surface.
"""

from app.blueprints.documents.routes import documents_bp

__all__ = ["documents_bp"]