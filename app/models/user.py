"""
user.py

SQLAlchemy ORM model representing a Student user (the primary end-user role)
of Minddora AI. Maps to the "users" table in PostgreSQL.

This model integrates with Flask-Login (via UserMixin) for session-based
authentication, and stores securely hashed passwords using Flask-Bcrypt
(hashing itself is performed in app/services/auth_service.py, never here).
"""

from datetime import datetime, timezone

from flask_login import UserMixin

from app.extensions import db


class User(db.Model, UserMixin):
    """
    Represents a student account.

    Table: users

    Relationships:
        documents      -> One-to-many with Document (a user owns many documents)
        chat_sessions  -> One-to-many with ChatSession
        feedback       -> One-to-many with Feedback
    """

    __tablename__ = "users"

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

    # Optional profile fields
    avatar_url = db.Column(db.String(500), nullable=True)
    institution = db.Column(db.String(255), nullable=True)
    field_of_study = db.Column(db.String(255), nullable=True)

    # -----------------------------------------------------------------
    # Account Status / Security
    # -----------------------------------------------------------------
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    is_email_verified = db.Column(db.Boolean, default=False, nullable=False)
    email_verification_token = db.Column(db.String(255), nullable=True)
    password_reset_token = db.Column(db.String(255), nullable=True)
    password_reset_expires_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # -----------------------------------------------------------------
    # Storage / Usage Quotas
    # -----------------------------------------------------------------
    storage_used_bytes = db.Column(db.BigInteger, default=0, nullable=False)
    # storage_quota_bytes = db.Column(db.BigInteger, default=500 * 1024 * 1024, nullable=False)  # 500 MB default
    storage_quota_bytes = db.Column(db.BigInteger, default=50 * 1024 * 1024, nullable=False)

    ai_mode = db.Column(db.String(20), default="local", nullable=False)  # "local" or "gemini"
    gemini_api_key = db.Column(db.String(255), nullable=True)
    gemini_model_name = db.Column(db.String(100), default="gemini-2.0-flash", nullable=True)


    ai_queries_used_this_month = db.Column(db.Integer, default=0, nullable=False)

    # -----------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_login_at = db.Column(db.DateTime(timezone=True), nullable=True)
    last_seen_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # -----------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------
    documents = db.relationship(
        "Document",
        backref="owner",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    chat_sessions = db.relationship(
        "ChatSession",
        backref="user",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )
    feedback_entries = db.relationship(
        "Feedback",
        backref="submitted_by",
        lazy="dynamic",
        cascade="all, delete-orphan",
    )

    # -----------------------------------------------------------------
    # Flask-Login required overrides
    # -----------------------------------------------------------------
    def get_id(self) -> str:
        """
        Overrides UserMixin.get_id() to prefix the ID with nothing for
        students (admins get an "admin-" prefix in the Admin model), so
        the user_loader callback in app/__init__.py can distinguish
        between the two roles sharing one login session mechanism.
        """
        return str(self.id)

    # -----------------------------------------------------------------
    # Convenience Methods
    # -----------------------------------------------------------------
    def storage_remaining_bytes(self) -> int:
        """Returns the number of bytes the user still has available for uploads."""
        return max(self.storage_quota_bytes - self.storage_used_bytes, 0)

    def has_storage_for(self, file_size_bytes: int) -> bool:
        """Checks whether uploading a file of the given size would exceed quota."""
        return (self.storage_used_bytes + file_size_bytes) <= self.storage_quota_bytes

    def is_online(self) -> bool:
        """Returns True if the user has been active within the last 5 minutes."""
        if not self.last_seen_at:
            return False
        from datetime import datetime, timezone, timedelta
        return (datetime.now(timezone.utc) - self.last_seen_at) < timedelta(minutes=5)

    # def to_dict(self) -> dict:
    #     """
    #     Serializes the user object to a JSON-safe dictionary for API responses.
    #     Excludes sensitive fields such as password_hash and reset tokens.
    #     """
    #     return {
    #         "id": self.id,
    #         "full_name": self.full_name,
    #         "email": self.email,
    #         "avatar_url": self.avatar_url,
    #         "institution": self.institution,
    #         "field_of_study": self.field_of_study,
    #         "is_email_verified": self.is_email_verified,
    #         "storage_used_bytes": self.storage_used_bytes,
    #         "storage_quota_bytes": self.storage_quota_bytes,
    #         "ai_queries_used_this_month": self.ai_queries_used_this_month,
    #         "created_at": self.created_at.isoformat() if self.created_at else None,
    #         "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
    #     }

    def to_dict(self) -> dict:
        """
        Serializes the user object to a JSON-safe dictionary for API responses.
        Excludes sensitive fields such as password_hash and reset tokens.
        """
        return {
            "id": self.id,
            "full_name": self.full_name,
            "email": self.email,
            "avatar_url": self.avatar_url,
            "institution": self.institution,
            "field_of_study": self.field_of_study,
            "is_active": self.is_active,
            "is_email_verified": self.is_email_verified,
            "storage_used_bytes": self.storage_used_bytes,
            "storage_quota_bytes": self.storage_quota_bytes,
            "ai_queries_used_this_month": self.ai_queries_used_this_month,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_login_at": self.last_login_at.isoformat() if self.last_login_at else None,
            "last_seen_at": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "is_online": self.is_online(),
            "ai_mode": self.ai_mode,
            "gemini_model_name": self.gemini_model_name,
            "has_gemini_key": bool(self.gemini_api_key),
        }

    
    @property
    def has_gemini_key(self) -> bool:
        """Returns True if this user has saved a Gemini API key."""
        return bool(self.gemini_api_key)
    
    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email}>"