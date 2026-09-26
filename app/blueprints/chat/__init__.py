"""
blueprints/chat/__init__.py

Re-exports the `chat_bp` Blueprint object defined in routes.py so it can
be imported cleanly from app/__init__.py as:

    from app.blueprints.chat import chat_bp

The Blueprint itself is instantiated in routes.py; this file exists
purely as the package's public import surface.
"""

from app.blueprints.chat.routes import chat_bp

__all__ = ["chat_bp"]