"""
document_service.py

Orchestration layer for the full document ingestion pipeline: upload
validation → storage → text extraction → cleaning → chunking →
embedding/vector storage → status finalization. Ties together
extraction_service.py, cleaning_service.py, chunking_service.py, and
embedding_service.py into a single callable used by the upload API/route
handlers (app/blueprints/api/document_api.py).

Also provides document listing, retrieval, and deletion (including
cascade cleanup of the associated vector store entries), used across the
"My Documents" page, Document Viewer, and duplicate-detection during
upload.
"""

import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.user import User
from app.services import extraction_service, cleaning_service, chunking_service, embedding_service, vector_store_service
# from app.utils.validators import validate_upload_file, compute_file_hash, get_file_extension, sanitize_plain_text
from app.utils.logger import log_to_db
from app.utils.validators import validate_upload_file, compute_file_hash, get_file_extension
from app.utils.security import sanitize_plain_text


class DocumentServiceError(Exception):
    """
    Raised for any expected failure during document upload or management
    (validation failure, storage quota exceeded, duplicate file, document
    not found, unauthorized access). Carries a machine-readable
    error_code for the calling API layer to map to the correct HTTP
    status and frontend error_code.
    """

    def __init__(self, message: str, error_code: str = "DOCUMENT_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# ---------------------------------------------------------------------------
# Upload Pipeline
# ---------------------------------------------------------------------------
def upload_document(
    user: User,
    file: FileStorage,
    upload_folder: str,
    max_file_size_bytes: int,
    title: Optional[str] = None,
    subject: Optional[str] = None,
) -> Document:
    """
    Validates, stores, and queues a newly uploaded file for full RAG
    ingestion processing (synchronously, in this implementation — see
    note below on background processing).

    Args:
        user: The authenticated Student (User) uploading the file.
        file: The Werkzeug FileStorage object from the multipart upload.
        upload_folder: Absolute path to store uploaded files, sourced
            from app.config["UPLOAD_FOLDER"].
        max_file_size_bytes: Maximum allowed file size, sourced from
            app.config["MAX_CONTENT_LENGTH"].
        title: Optional user-supplied document title; defaults to the
            original filename (without extension) if not provided.
        subject: Optional user-supplied subject/category tag.

    Returns:
        The created Document instance, with processing_status reflecting
        the outcome ("ready" on success, "failed" with processing_error
        set if any pipeline stage failed).

    Raises:
        DocumentServiceError: If basic validation fails, storage quota is
            exceeded, or the file is a duplicate of an existing document.

    Note on synchronous processing:
        This implementation runs extraction/chunking/embedding inline
        within the request for simplicity. For production traffic at
        scale, this call should be dispatched to a background task queue
        (e.g. Celery + Redis) so large PDF uploads don't block the HTTP
        request/worker thread — noted in the Future Features roadmap.
    """
    validation_error = validate_upload_file(file, max_file_size_bytes)
    if validation_error:
        raise DocumentServiceError(validation_error, "INVALID_FILE")

    file.stream.seek(0, os.SEEK_END)
    file_size = file.stream.tell()
    file.stream.seek(0)

    if not user.has_storage_for(file_size):
        raise DocumentServiceError(
            "This upload would exceed your storage quota. Please delete some documents or upgrade your plan.",
            "STORAGE_QUOTA_EXCEEDED",
        )

    file_hash = compute_file_hash(file)
    existing_duplicate = Document.query.filter_by(user_id=user.id, file_hash=file_hash, is_deleted=False).first()
    if existing_duplicate is not None:
        raise DocumentServiceError(
            f"You've already uploaded this file as '{existing_duplicate.original_filename}'.",
            "DUPLICATE_FILE",
        )

    stored_filename, file_path = _save_file_to_disk(file, upload_folder)
    file_type = get_file_extension(file.filename)

    document = Document(
        user_id=user.id,
        original_filename=sanitize_plain_text(file.filename),
        stored_filename=stored_filename,
        file_path=file_path,
        file_type=file_type,
        file_size_bytes=file_size,
        file_hash=file_hash,
        title=sanitize_plain_text(title) if title else os.path.splitext(file.filename)[0],
        subject=sanitize_plain_text(subject) if subject else None,
        processing_status="queued",
    )

    db.session.add(document)
    db.session.commit()

    user.storage_used_bytes += file_size
    db.session.commit()

    log_to_db(
        level="INFO",
        category="upload",
        message=f"UPLOAD: {user.full_name} ({user.email}) uploaded '{document.original_filename}'.",
        user_id=user.id,
    )

    _run_ingestion_pipeline(document)

    return document
    # db.session.add(document)
    # db.session.commit()

    # user.storage_used_bytes += file_size
    # db.session.commit()

    # _run_ingestion_pipeline(document)

    # return document


def _save_file_to_disk(file: FileStorage, upload_folder: str) -> tuple:
    """
    Persists the uploaded file to disk under a UUID-based filename (to
    avoid collisions and path-traversal risk from user-supplied
    filenames), while preserving the original extension.

    Args:
        file: The Werkzeug FileStorage object.
        upload_folder: Absolute path to the uploads directory.

    Returns:
        A tuple of (stored_filename, absolute_file_path).
    """
    os.makedirs(upload_folder, exist_ok=True)

    original_secure_name = secure_filename(file.filename)
    extension = get_file_extension(original_secure_name)
    stored_filename = f"{uuid.uuid4().hex}.{extension}"
    file_path = os.path.join(upload_folder, stored_filename)

    file.save(file_path)

    return stored_filename, file_path


def _run_ingestion_pipeline(document: Document) -> None:
    """
    Runs the full extraction -> cleaning -> chunking -> embedding
    pipeline for a newly uploaded Document, updating its
    processing_status at each stage and capturing any failure with a
    user-facing error message.

    Args:
        document: The Document instance to process (already persisted
            with processing_status="queued").
    """
    try:
        document.mark_status("extracting")
        db.session.commit()
        raw_pages = extraction_service.extract_text(document.file_path, document.file_type)
        document.page_count = len(raw_pages)

        cleaned_pages = cleaning_service.clean_pages(raw_pages)

        document.mark_status("chunking")
        db.session.commit()
        from flask import current_app
        raw_chunks = chunking_service.chunk_document_pages(
            cleaned_pages,
            chunk_size_tokens=current_app.config["CHUNK_SIZE"],
            chunk_overlap_tokens=current_app.config["CHUNK_OVERLAP"],
        )

        document.mark_status("embedding")
        db.session.commit()
        total_chunks = embedding_service.embed_and_store_chunks(
            document_id=document.id,
            user_id=document.user_id,
            raw_chunks=raw_chunks,
            embedding_model_name=current_app.config["EMBEDDING_MODEL_NAME"],
        )
        document.total_chunks = total_chunks

        document.mark_status("ready")
        db.session.commit()

        log_to_db(
            level="INFO",
            category="rag_pipeline",
            message=f"Document {document.id} processed successfully with {total_chunks} chunks.",
            user_id=document.user_id,
        )

    except (extraction_service.ExtractionError, embedding_service.EmbeddingError) as exc:
        db.session.rollback()
        document.mark_status("failed", error=exc.message)
        db.session.commit()
        log_to_db(
            level="ERROR",
            category="rag_pipeline",
            message=f"Document {document.id} processing failed: {exc.message}",
            user_id=document.user_id,
        )
    except Exception as exc:  # noqa: BLE001 — catch-all so one bad document never crashes the request
        db.session.rollback()
        document.mark_status("failed", error="An unexpected error occurred while processing this document.")
        db.session.commit()
        log_to_db(
            level="ERROR",
            category="rag_pipeline",
            message=f"Document {document.id} processing failed unexpectedly: {exc}",
            user_id=document.user_id,
        )


# ---------------------------------------------------------------------------
# Listing / Retrieval
# ---------------------------------------------------------------------------
def get_user_documents(user_id: int, page: int = 1, per_page: int = 20, subject_filter: Optional[str] = None) -> tuple:
    """
    Retrieves a paginated list of a student's non-deleted documents for
    the "My Documents" page.

    Args:
        user_id: The requesting student's ID.
        page: 1-indexed page number.
        per_page: Number of documents per page.
        subject_filter: Optional exact-match subject/category filter.

    Returns:
        A tuple of (documents: List[Document], total_count: int).
    """
    query = Document.query.filter_by(user_id=user_id, is_deleted=False)
    if subject_filter:
        query = query.filter_by(subject=subject_filter)

    query = query.order_by(Document.uploaded_at.desc())

    total_count = query.count()
    documents = query.offset((page - 1) * per_page).limit(per_page).all()

    return documents, total_count


def get_document_by_id(document_id: int, user_id: int) -> Document:
    """
    Retrieves a single document, enforcing that it belongs to the
    requesting user (ownership check) and has not been soft-deleted.

    Args:
        document_id: The Document.id to retrieve.
        user_id: The requesting student's ID.

    Returns:
        The Document instance.

    Raises:
        DocumentServiceError: If no matching, non-deleted document owned
            by this user exists.
    """
    document = Document.query.filter_by(id=document_id, user_id=user_id, is_deleted=False).first()
    if document is None:
        raise DocumentServiceError("Document not found or you do not have access to it.", "DOCUMENT_NOT_FOUND")
    return document


# ---------------------------------------------------------------------------
# Deletion
# ---------------------------------------------------------------------------
def delete_document(document_id: int, user_id: int) -> None:
    """
    Soft-deletes a document and cascades cleanup to the vector store,
    removing all of its chunks' vectors so they can no longer surface in
    future chat/search results, and reclaims the user's storage quota.

    Args:
        document_id: The Document.id to delete.
        user_id: The requesting student's ID (ownership enforcement).

    Raises:
        DocumentServiceError: If the document is not found or not owned
            by this user.
    """
    document = get_document_by_id(document_id, user_id)

    chunk_vector_ids = [c.vector_id for c in document.chunks.all()]
    if chunk_vector_ids:
        vector_store_service.remove_vectors(chunk_vector_ids)

    user = User.query.get(user_id)
    if user is not None:
        user.storage_used_bytes = max(user.storage_used_bytes - document.file_size_bytes, 0)

    # Remove the physical file from disk; failure to do so is logged but
    # does not block the deletion from completing in the database.
    try:
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
    except OSError as exc:
        log_to_db(
            level="WARNING",
            category="upload",
            message=f"Failed to remove file from disk for document {document_id}: {exc}",
            user_id=user_id,
        )

    document.is_deleted = True
    db.session.commit()

    user = User.query.get(user_id)
    log_to_db(
        level="INFO",
        category="upload",
        message=f"DELETE: {user.full_name} ({user.email}) deleted '{document.original_filename}'.",
        user_id=user_id,
    )
    # document.is_deleted = True
    # db.session.commit()

    # log_to_db(level="INFO", category="upload", message=f"Document {document_id} deleted by user.", user_id=user_id)


def reprocess_document(document_id: int, user_id: int) -> Document:
    """
    Re-runs the full ingestion pipeline for a document that previously
    failed processing (e.g. after a transient error), used by a "Retry"
    button on the "My Documents" page. First removes any partially
    created chunks/vectors from the failed attempt to avoid duplicates.

    Args:
        document_id: The Document.id to reprocess.
        user_id: The requesting student's ID (ownership enforcement).

    Returns:
        The Document instance after reprocessing completes.

    Raises:
        DocumentServiceError: If the document is not found or not owned
            by this user.
    """
    document = get_document_by_id(document_id, user_id)

    existing_chunks = document.chunks.all()
    if existing_chunks:
        vector_store_service.remove_vectors([c.vector_id for c in existing_chunks])
        for chunk in existing_chunks:
            db.session.delete(chunk)
        db.session.commit()

    document.processing_error = None
    document.total_chunks = 0
    document.mark_status("queued")
    db.session.commit()

    _run_ingestion_pipeline(document)

    return document