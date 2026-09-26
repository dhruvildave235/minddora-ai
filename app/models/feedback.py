"""
feedback.py

SQLAlchemy ORM model representing user-submitted feedback (bug reports,
feature requests, general comments, or per-answer ratings). Maps to the
"feedback" table in PostgreSQL. Reviewed by admins via the Feedback
Management page in the Admin Panel.
"""

from datetime import datetime, timezone

from app.extensions import db


class Feedback(db.Model):
    """
    Represents a single feedback submission from a student.

    Table: feedback

    Relationships:
        (backref "submitted_by" is defined on User.feedback_entries)
    """

    __tablename__ = "feedback"

    # id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    guest_name = db.Column(db.String(120), nullable=True)
    guest_email = db.Column(db.String(255), nullable=True)

    # -----------------------------------------------------------------
    # Feedback Classification
    # -----------------------------------------------------------------
    # "bug" | "feature_request" | "general" | "answer_rating"
    category = db.Column(db.String(30), nullable=False, default="general")
    subject = db.Column(db.String(255), nullable=False)
    message = db.Column(db.Text, nullable=False)

    # -----------------------------------------------------------------
    # Optional Link to a Specific AI Answer (for answer_rating feedback)
    # -----------------------------------------------------------------
    chat_message_id = db.Column(db.Integer, db.ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    rating = db.Column(db.Integer, nullable=True)  # 1-5 stars, only used for answer_rating category

    # -----------------------------------------------------------------
    # Admin Review Workflow
    # -----------------------------------------------------------------
    # "open" -> "in_review" -> "resolved" | "dismissed"
    status = db.Column(db.String(20), default="open", nullable=False, index=True)
    admin_response = db.Column(db.Text, nullable=True)
    reviewed_by_admin_id = db.Column(db.Integer, db.ForeignKey("admins.id", ondelete="SET NULL"), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # -----------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def mark_reviewed(self, admin_id: int, response: str, new_status: str = "resolved") -> None:
        """
        Updates the feedback record once an admin has reviewed it. Called
        from app/blueprints/admin/routes.py or the Admin Feedback API.
        """
        self.status = new_status
        self.admin_response = response
        self.reviewed_by_admin_id = admin_id
        self.reviewed_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Serializes the feedback entry to a JSON-safe dictionary for API responses."""
        return {
            # "id": self.id,
            # "user_id": self.user_id,
            "id": self.id,
            "user_id": self.user_id,
            "guest_name": self.guest_name,
            "guest_email": self.guest_email,
            "category": self.category,
            "subject": self.subject,
            "message": self.message,
            "chat_message_id": self.chat_message_id,
            "rating": self.rating,
            "status": self.status,
            "admin_response": self.admin_response,
            "reviewed_by_admin_id": self.reviewed_by_admin_id,
            "reviewed_at": self.reviewed_at.isoformat() if self.reviewed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Feedback id={self.id} user_id={self.user_id} category={self.category} status={self.status}>"