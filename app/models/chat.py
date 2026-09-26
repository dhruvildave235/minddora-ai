"""
chat.py

SQLAlchemy ORM models representing AI chat conversations. Maps to two
PostgreSQL tables:

    chat_sessions -> A conversation thread belonging to a user (optionally
                      scoped to a single document, or spanning all of the
                      user's documents).
    chat_messages -> Individual question/answer turns within a session,
                      including retrieved citations and confidence scores.

Splitting sessions and messages into two tables (rather than one flat
"chat_history" table) allows the UI to group conversations (History /
Saved Conversations pages), support renaming/bookmarking a whole thread,
and paginate messages independently of session metadata.
"""

from datetime import datetime, timezone

from app.extensions import db


class ChatSession(db.Model):
    """
    Represents one conversation thread between a student and the AI.

    Table: chat_sessions

    Relationships:
        messages -> One-to-many with ChatMessage
        (backref "user" is defined on User.chat_sessions)
    """

    __tablename__ = "chat_sessions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # Optional scope: if set, this session only queries chunks from this one
    # document; if null, the session searches across ALL of the user's documents.
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)

    title = db.Column(db.String(255), default="New Conversation", nullable=False)
    is_bookmarked = db.Column(db.Boolean, default=False, nullable=False, index=True)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # -----------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------
    messages = db.relationship(
        "ChatMessage",
        backref="session",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )

    def to_dict(self, include_messages: bool = False) -> dict:
        """Serializes the session to a JSON-safe dictionary for API responses."""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "document_id": self.document_id,
            "title": self.title,
            "is_bookmarked": self.is_bookmarked,
            "is_archived": self.is_archived,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": self.messages.count(),
        }
        if include_messages:
            data["messages"] = [m.to_dict() for m in self.messages]
        return data

    def __repr__(self) -> str:
        return f"<ChatSession id={self.id} user_id={self.user_id} title={self.title!r}>"


class ChatMessage(db.Model):
    """
    Represents a single question/answer turn within a ChatSession.

    Table: chat_messages

    Relationships:
        (backref "session" is defined on ChatSession.messages)
    """

    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    session_id = db.Column(db.Integer, db.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False, index=True)

    # "user" or "assistant"
    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)

    # -----------------------------------------------------------------
    # RAG Metadata (populated only on "assistant" messages)
    # -----------------------------------------------------------------
    # JSONB column storing a list of citation objects, e.g.:
    # [{"document_id": 12, "chunk_id": 88, "page_number": 4, "excerpt": "..."}]
    citations = db.Column(db.JSON, nullable=True)
    confidence_score = db.Column(db.Float, nullable=True)  # 0.0 - 1.0, derived from retrieval similarity
    retrieval_chunk_count = db.Column(db.Integer, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    def to_dict(self) -> dict:
        """Serializes the message to a JSON-safe dictionary for API responses."""
        return {
            "id": self.id,
            "session_id": self.session_id,
            "role": self.role,
            "content": self.content,
            "citations": self.citations,
            "confidence_score": self.confidence_score,
            "retrieval_chunk_count": self.retrieval_chunk_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} session_id={self.session_id} role={self.role}>"