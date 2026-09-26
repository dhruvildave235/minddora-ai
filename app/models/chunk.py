"""
chunk.py

SQLAlchemy ORM model representing a single text chunk derived from a
Document during the RAG ingestion pipeline. Maps to the "chunks" table
in PostgreSQL.

Design note on vector storage:
    The actual embedding VECTOR (a 384-dimension float array from
    all-MiniLM-L6-v2) is NOT stored in PostgreSQL in this schema — it is
    stored in the vector database (FAISS index file or ChromaDB collection)
    for fast similarity search. This "chunks" table stores the chunk's
    raw TEXT and STRUCTURAL METADATA (page number, position, source
    document), and holds a `vector_id` foreign key/reference that links
    each row to its corresponding vector inside the vector store, so a
    similarity search result can be resolved back to full chunk text,
    source document, and page number for citation display.
"""

from datetime import datetime, timezone

from app.extensions import db


class Chunk(db.Model):
    """
    Represents one semantically-chunked piece of text extracted from a Document.

    Table: chunks

    Relationships:
        (backref "document" is defined on Document.chunks)
    """

    __tablename__ = "chunks"

    # -----------------------------------------------------------------
    # Primary Key / Ownership
    # -----------------------------------------------------------------
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    document_id = db.Column(db.Integer, db.ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    # -----------------------------------------------------------------
    # Chunk Content & Position
    # -----------------------------------------------------------------
    chunk_index = db.Column(db.Integer, nullable=False)          # Order of this chunk within the document (0-based)
    chunk_text = db.Column(db.Text, nullable=False)
    chunk_char_length = db.Column(db.Integer, nullable=False)
    page_number = db.Column(db.Integer, nullable=True)           # Source page, if applicable (PDF/DOCX)

    # -----------------------------------------------------------------
    # Vector Store Linkage
    # -----------------------------------------------------------------
    # Unique string ID used as the key/reference inside FAISS (row index
    # mapping) or ChromaDB (native document ID) so a retrieved vector can
    # be resolved back to this row.
    vector_id = db.Column(db.String(100), nullable=False, unique=True, index=True)
    embedding_model = db.Column(db.String(100), default="all-MiniLM-L6-v2", nullable=False)

    # -----------------------------------------------------------------
    # Timestamps
    # -----------------------------------------------------------------
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    # -----------------------------------------------------------------
    # Convenience Methods
    # -----------------------------------------------------------------
    def to_dict(self, include_text: bool = True) -> dict:
        """
        Serializes the chunk to a JSON-safe dictionary.

        Args:
            include_text: When False, omits the full chunk_text (useful for
                lightweight listings where only metadata is needed).
        """
        data = {
            "id": self.id,
            "document_id": self.document_id,
            "chunk_index": self.chunk_index,
            "chunk_char_length": self.chunk_char_length,
            "page_number": self.page_number,
            "vector_id": self.vector_id,
            "embedding_model": self.embedding_model,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
        if include_text:
            data["chunk_text"] = self.chunk_text
        return data

    def to_citation(self) -> dict:
        """
        Returns a compact citation payload used in Chat API responses,
        pointing the user back to the exact source of an AI answer.
        """
        return {
            "document_id": self.document_id,
            "chunk_id": self.id,
            "page_number": self.page_number,
            "excerpt": (self.chunk_text[:200] + "...") if len(self.chunk_text) > 200 else self.chunk_text,
        }

    def __repr__(self) -> str:
        return f"<Chunk id={self.id} document_id={self.document_id} index={self.chunk_index}>"