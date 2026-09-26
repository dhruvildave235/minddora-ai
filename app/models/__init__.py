"""
models/__init__.py

Central import point for all SQLAlchemy ORM models in Minddora AI.

Importing every model here ensures that:
    1. All models are registered on the shared SQLAlchemy metadata
       (app.extensions.db) before Flask-Migrate generates or applies
       migrations against PostgreSQL — otherwise Alembic's autogenerate
       would miss tables that were never imported anywhere.
    2. Other modules can import models from a single, stable path, e.g.:
           from app.models import User, Admin, Document, Chunk, \
               ChatSession, ChatMessage, Feedback, SystemLog
       instead of reaching into each individual submodule.

This module intentionally contains no logic — it only re-exports.
"""

from app.models.user import User
from app.models.admin import Admin
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.chat import ChatSession, ChatMessage
from app.models.feedback import Feedback
from app.models.log import SystemLog

__all__ = [
    "User",
    "Admin",
    "Document",
    "Chunk",
    "ChatSession",
    "ChatMessage",
    "Feedback",
    "SystemLog",
]