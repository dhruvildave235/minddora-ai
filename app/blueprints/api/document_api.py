"""
document_api.py

JSON REST API endpoints for document upload, listing, viewing, deletion,
and reprocessing — consumed by the frontend's static/js/upload.js and
static/js/dashboard.js via fetch() calls. Every endpoint returns the
standardized response envelope from app/utils/responses.py and enforces
student-only access via @student_required.

Registered under url_prefix="/api/documents" in app/__init__.py, so full
paths are e.g. POST /api/documents/upload, GET /api/documents, etc.
"""

from flask import Blueprint, request, current_app
from flask_login import current_user

from app.services import document_service
from app.services.document_service import DocumentServiceError
from app.utils.responses import success_response, error_response, paginated_response
from app.utils.decorators import student_required, active_account_required
from app.extensions import limiter

document_api_bp = Blueprint("document_api", __name__)


@document_api_bp.route("/upload", methods=["POST"])
@student_required
@active_account_required
@limiter.limit("30 per hour")
def api_upload_document():
    """
    POST /api/documents/upload

    Multipart form-data request:
        file: the uploaded file (PDF, DOCX, TXT, MD, PNG, JPG, JPEG)
        title: optional string
        subject: optional string

    Success (201): { "success": true, "data": {"document": {...}}, "message": "..." }
    Error (400/409/413): { "success": false, "error": "...", "error_code": "..." }
    """
    if "file" not in request.files:
        return error_response("No file was included in the upload request.", status_code=400, error_code="NO_FILE")

    file = request.files["file"]
    title = request.form.get("title")
    subject = request.form.get("subject")

    try:
        document = document_service.upload_document(
            user=current_user,
            file=file,
            upload_folder=current_app.config["UPLOAD_FOLDER"],
            max_file_size_bytes=current_app.config["MAX_CONTENT_LENGTH"],
            title=title,
            subject=subject,
        )
        return success_response(
            data={"document": document.to_dict()},
            message="Document uploaded and processed successfully.",
            status_code=201,
        )
    except DocumentServiceError as exc:
        status = {
            "STORAGE_QUOTA_EXCEEDED": 413,
            "DUPLICATE_FILE": 409,
        }.get(exc.error_code, 400)
        return error_response(exc.message, status_code=status, error_code=exc.error_code)


@document_api_bp.route("", methods=["GET"])
@student_required
def api_list_documents():
    """
    GET /api/documents?page=1&per_page=20&subject=Physics

    Query params:
        page: 1-indexed page number (default 1)
        per_page: results per page (default 20, max 100)
        subject: optional exact-match subject filter

    Success (200): Paginated response with {"items": [...], "pagination": {...}}
    """
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    subject_filter = request.args.get("subject")

    documents, total_count = document_service.get_user_documents(
        user_id=current_user.id, page=page, per_page=per_page, subject_filter=subject_filter
    )

    return paginated_response(
        items=[doc.to_dict() for doc in documents],
        page=page,
        per_page=per_page,
        total_items=total_count,
    )


@document_api_bp.route("/<int:document_id>", methods=["GET"])
@student_required
def api_get_document(document_id):
    """
    GET /api/documents/<document_id>

    Success (200): { "success": true, "data": {"document": {...}} }
    Error (404): { "success": false, "error": "...", "error_code": "DOCUMENT_NOT_FOUND" }
    """
    include_chunks = request.args.get("include_chunks", "false").lower() == "true"

    try:
        document = document_service.get_document_by_id(document_id, current_user.id)
        return success_response(data={"document": document.to_dict(include_chunks=include_chunks)})
    except DocumentServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)


@document_api_bp.route("/<int:document_id>", methods=["DELETE"])
@student_required
@active_account_required
def api_delete_document(document_id):
    """
    DELETE /api/documents/<document_id>

    Soft-deletes the document, cascades vector store cleanup, and
    reclaims storage quota.

    Success (200): { "success": true, "message": "..." }
    Error (404): { "success": false, "error": "...", "error_code": "DOCUMENT_NOT_FOUND" }
    """
    try:
        document_service.delete_document(document_id, current_user.id)
        return success_response(message="Document deleted successfully.")
    except DocumentServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)


@document_api_bp.route("/<int:document_id>/reprocess", methods=["POST"])
@student_required
@active_account_required
@limiter.limit("10 per hour")
def api_reprocess_document(document_id):
    """
    POST /api/documents/<document_id>/reprocess

    Re-runs the full ingestion pipeline for a previously failed document
    (a "Retry" action on the My Documents page).

    Success (200): { "success": true, "data": {"document": {...}}, "message": "..." }
    Error (404): { "success": false, "error": "...", "error_code": "DOCUMENT_NOT_FOUND" }
    """
    try:
        document = document_service.reprocess_document(document_id, current_user.id)
        return success_response(data={"document": document.to_dict()}, message="Document reprocessing complete.")
    except DocumentServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)


@document_api_bp.route("/<int:document_id>/status", methods=["GET"])
@student_required
def api_document_status(document_id):
    """
    GET /api/documents/<document_id>/status

    Lightweight polling endpoint used by upload.js to show a live
    processing status indicator ("Extracting...", "Chunking...",
    "Embedding...", "Ready") without re-fetching full document metadata.

    Success (200): { "success": true, "data": {"processing_status": "...",
                      "processing_error": null, "total_chunks": 12} }
    Error (404): { "success": false, "error": "...", "error_code": "DOCUMENT_NOT_FOUND" }
    """
    try:
        document = document_service.get_document_by_id(document_id, current_user.id)
        return success_response(data={
            "processing_status": document.processing_status,
            "processing_error": document.processing_error,
            "total_chunks": document.total_chunks,
        })
    except DocumentServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)