"""
log.py

SQLAlchemy ORM model representing a system-level log/audit event. Maps to
the "system_logs" table in PostgreSQL. Populated by app/utils/logger.py's
database log handler for events worth persisting and querying (errors,
security events, admin actions), as opposed to routine debug/info logs
which go to rotating file logs on disk only (storage/logs/).

Used by the Admin Panel's "Error Logs" / "System Logs" page for filtering,
searching, and monitoring platform health.
"""

from datetime import datetime, timezone

from app.extensions import db


class SystemLog(db.Model):
    """
    Represents a single persisted system event (error, security event,
    or significant admin action).

    Table: system_logs
    """

    __tablename__ = "system_logs"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # -----------------------------------------------------------------
    # Classification
    # -----------------------------------------------------------------
    # "DEBUG" | "INFO" | "WARNING" | "ERROR" | "CRITICAL"
    level = db.Column(db.String(20), nullable=False, index=True)

    # "auth" | "upload" | "rag_pipeline" | "chat" | "admin_action" |
    # "security" | "database" | "system"
    category = db.Column(db.String(50), nullable=False, index=True)

    message = db.Column(db.Text, nullable=False)

    # -----------------------------------------------------------------
    # Contextual Metadata
    # -----------------------------------------------------------------
    # JSONB payload for structured extra context, e.g.
    # {"endpoint": "/api/documents/upload", "status_code": 500, "traceback": "..."}
    context = db.Column(db.JSON, nullable=True)

    # Nullable — not every log event is tied to a specific user or admin
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    admin_id = db.Column(db.Integer, db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True)

    ip_address = db.Column(db.String(45), nullable=True)  # Supports IPv6
    request_path = db.Column(db.String(500), nullable=True)

    # -----------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    def to_dict(self) -> dict:
        """Serializes the log entry to a JSON-safe dictionary for the Admin Panel API."""
        return {
            "id": self.id,
            "level": self.level,
            "category": self.category,
            "message": self.message,
            "context": self.context,
            "user_id": self.user_id,
            "admin_id": self.admin_id,
            "ip_address": self.ip_address,
            "request_path": self.request_path,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<SystemLog id={self.id} level={self.level} category={self.category}>"