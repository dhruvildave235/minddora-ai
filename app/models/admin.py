"""
admin.py

SQLAlchemy ORM model representing an Admin account. Maps to the "admins"
table in PostgreSQL. Kept as a fully separate table (rather than a role
flag on the "users" table) so that admin authentication, permissions, and
audit trail remain isolated from the student-facing User model — reducing
the risk of privilege-escalation bugs.
"""

from datetime import datetime, timezone

from flask_login import UserMixin

from app.extensions import db


class Admin(db.Model, UserMixin):
    """
    Represents a platform administrator account.

    Table: admins

    Relationships:
        logs_reviewed -> One-to-many with SystemLog (logs acknowledged by this admin)
    """

    __tablename__ = "admins"

    # -----------------------------------------------------------------
    # Primary Key
    # -----------------------------------------------------------------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # -----------------------------------------------------------------
    # Core Profile Fields
    # -----------------------------------------------------------------
    full_name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)

    # -----------------------------------------------------------------
    # Role / Permission Level
    # -----------------------------------------------------------------
    # "super_admin"  -> full system access, including settings + other admins
    # "support_admin" -> user/document/feedback management, no system settings
    # "analyst"       -> read-only access to analytics and logs
    role = db.Column(db.String(50), default="support_admin", nullable=False)

    is_active = db.Column(db.Boolean, default=True, nullable=False)

    # -----------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # -----------------------------------------------------------------
    # Flask-Login required overrides
    # -----------------------------------------------------------------
    def get_id(self) -> str:
        """
        Prefixes the admin's ID with "admin-" so the shared user_loader
        callback in app/__init__.py can distinguish an Admin session from
        a Student (User) session, since both roles use Flask-Login against
        the same PostgreSQL-backed session store.
        """
        return f"admin-{self.id}"

    # -----------------------------------------------------------------
    # Permission Helpers
    # -----------------------------------------------------------------
    def is_super_admin(self) -> bool:
        return self.role == "super_admin"

    def can_manage_users(self) -> bool:
        return self.role in ("super_admin", "support_admin")

    def can_manage_settings(self) -> bool:
        return self.role == "super_admin"

    def can_view_analytics(self) -> bool:
        return self.role in ("super_admin", "support_admin", "analyst")

    # -----------------------------------------------------------------
    # Serialization
    # -----------------------------------------------------------------
    def to_dict(self) -> dict:
        """Serializes the admin object to a JSON-safe dictionary for API responses."""
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "role": self.role,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
        }

    def __repr__(self) -> str:
        return f"<Admin id={self.id} email={self.email} role={self.role}>"