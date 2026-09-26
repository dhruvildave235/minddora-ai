"""
document.py

SQLAlchemy ORM model representing an uploaded study document. Maps to the
"documents" table in PostgreSQL. Each Document belongs to exactly one User
(student) and has many Chunk records once it has been processed by the
RAG ingestion pipeline (extraction -> cleaning -> chunking -> embedding).
"""

from datetime import datetime, timezone

from app.extensions import db


class Document(db.Model):
    """
    Represents a single uploaded study document (PDF, DOCX, TXT, MD, or image).

    Table: documents

    Relationships:
        chunks -> One-to-many with Chunk (all text chunks derived from this document)
    """

    __tablename__ = "documents"

    # -----------------------------------------------------------------
    # Primary Key / Ownership
    # -----------------------------------------------------------------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # -----------------------------------------------------------------
    # File Metadata
    # -----------------------------------------------------------------
    original_filename = db.Column(db.String(500), nullable=False)
    stored_filename = db.Column(db.String(500), nullable=False, unique=True)  # UUID-based name on disk
    file_path = db.Column(db.String(1000), nullable=False)  # Absolute path under storage/uploads/
    file_type = db.Column(db.String(20), nullable=False)    # pdf | docx | txt | md | png | jpg | jpeg
    file_size_bytes = db.Column(db.BigInteger, nullable=False)
    file_hash = db.Column(db.String(64), nullable=False, index=True)  # SHA-256, used for duplicate detection

    # -----------------------------------------------------------------
    # Organizational Metadata
    # -----------------------------------------------------------------
    title = db.Column(db.String(500), nullable=True)      # Optional user-friendly title
    subject = db.Column(db.String(255), nullable=True)     # Optional subject/category tag
    page_count = db.Column(db.Integer, nullable=True)

    # -----------------------------------------------------------------
    # Processing Pipeline Status
    # -----------------------------------------------------------------
    # "queued" -> "extracting" -> "chunking" -> "embedding" -> "ready" | "failed"
    processing_status = db.Column(db.String(20), default="queued", nullable=False, index=True)
    processing_error = db.Column(db.Text, nullable=True)
    total_chunks = db.Column(db.Integer, default=0, nullable=False)

    # -----------------------------------------------------------------
    # Soft Delete Flag
    # -----------------------------------------------------------------
    is_deleted = db.Column(db.Boolean, default=False, nullable=False, index=True)

    # -----------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------
    uploaded_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    processed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # -----------------------------------------------------------------
    # Relationships
    # -----------------------------------------------------------------
    chunks = db.relationship(
        "Chunk",
        backref="document",
        lazy="dynamic",
        cascade="all, delete-orphan",
        order_by="Chunk.chunk_index",
    )

    # -----------------------------------------------------------------
    # Convenience Methods
    # -----------------------------------------------------------------
    def mark_status(self, status: str, error: str = None) -> None:
        """
        Updates the processing_status field and, on completion, sets
        processed_at. Called by the document ingestion pipeline
        (app/services/document_service.py) as the document moves through
        extraction, chunking, and embedding stages.
        """
        self.processing_status = status
        if status == "failed" and error:
            self.processing_error = error
        if status == "ready":
            self.processed_at = datetime.now(timezone.utc)

    def to_dict(self, include_chunks: bool = False) -> dict:
        """Serializes the document object to a JSON-safe dictionary for API responses."""
        data = {
            "id": self.id,
            "user_id": self.user_id,
            "original_filename": self.original_filename,
            "file_type": self.file_type,
            "file_size_bytes": self.file_size_bytes,
            "title": self.title,
            "subject": self.subject,
            "page_count": self.page_count,
            "processing_status": self.processing_status,
            "processing_error": self.processing_error,
            "total_chunks": self.total_chunks,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
            "processed_at": self.processed_at.isoformat() if self.processed_at else None,
        }
        if include_chunks:
            data["chunks"] = [chunk.to_dict() for chunk in self.chunks]
        return data

    def __repr__(self) -> str:
        return f"<Document id={self.id} filename={self.original_filename} status={self.processing_status}>"