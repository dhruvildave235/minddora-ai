"""
chat_api.py

JSON REST API endpoints for the AI Chat feature — consumed by the
frontend's static/js/chat.js via fetch() calls. Handles sending a chat
message (running the full hybrid retrieval + extractive answer pipeline),
listing/retrieving chat sessions, and session management actions
(rename, bookmark, archive). Every endpoint returns the standardized
response envelope from app/utils/responses.py and enforces student-only
access via @student_required.

Registered under url_prefix="/api/chat" in app/__init__.py, so full paths
are e.g. POST /api/chat/message, GET /api/chat/sessions, etc.
"""

from flask import Blueprint, request, current_app
from flask_login import current_user

from app.services import chat_service
from app.services.chat_service import ChatServiceError
from app.utils.responses import success_response, error_response, paginated_response
from app.utils.decorators import student_required, active_account_required, json_required
from app.extensions import limiter

chat_api_bp = Blueprint("chat_api", __name__)


@chat_api_bp.route("/message", methods=["POST"])
@student_required
@active_account_required
@limiter.limit("60 per hour")
@json_required
def api_send_message():
    """
    POST /api/chat/message

    Request JSON body:
        {
            "question": "What is the second law of thermodynamics?",
            "session_id": 42,          // optional — omit to start a new session
            "document_id": 7            // optional — scopes a NEW session to one document
        }

    Success (200):
        {
            "success": true,
            "data": {
                "session": {...},
                "user_message": {...},
                "assistant_message": {...}
            }
        }
    Error (400/404): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}

    try:
        result = chat_service.send_message(
            user_id=current_user.id,
            question=payload.get("question"),
            session_id=payload.get("session_id"),
            document_id=payload.get("document_id"),
            top_k=current_app.config["TOP_K_RETRIEVAL"],
            similarity_threshold=current_app.config["SIMILARITY_THRESHOLD"],
            embedding_model_name=current_app.config["EMBEDDING_MODEL_NAME"],
        )
        return success_response(data=result)
    except ChatServiceError as exc:
        status = 404 if exc.error_code in ("SESSION_NOT_FOUND", "DOCUMENT_NOT_FOUND") else 400
        return error_response(exc.message, status_code=status, error_code=exc.error_code)


@chat_api_bp.route("/sessions", methods=["GET"])
@student_required
def api_list_sessions():
    """
    GET /api/chat/sessions?page=1&per_page=20&bookmarked_only=false

    Query params:
        page: 1-indexed page number (default 1)
        per_page: results per page (default 20, max 100)
        bookmarked_only: "true" to restrict to the Saved Conversations page

    Success (200): Paginated response with {"items": [...], "pagination": {...}}
    """
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    bookmarked_only = request.args.get("bookmarked_only", "false").lower() == "true"

    sessions, total_count = chat_service.get_user_sessions(
        user_id=current_user.id, page=page, per_page=per_page, bookmarked_only=bookmarked_only
    )

    return paginated_response(
        items=[s.to_dict() for s in sessions],
        page=page,
        per_page=per_page,
        total_items=total_count,
    )


@chat_api_bp.route("/sessions/<int:session_id>", methods=["GET"])
@student_required
def api_get_session(session_id):
    """
    GET /api/chat/sessions/<session_id>

    Returns the full session with its complete message history, used
    when the student opens a conversation from the History page.

    Success (200): { "success": true, "data": {"session": {...}} }
    Error (404): { "success": false, "error": "...", "error_code": "SESSION_NOT_FOUND" }
    """
    try:
        session = chat_service.get_session_with_messages(session_id, current_user.id)
        return success_response(data={"session": session.to_dict(include_messages=True)})
    except ChatServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)


@chat_api_bp.route("/sessions/<int:session_id>/rename", methods=["POST"])
@student_required
@json_required
def api_rename_session(session_id):
    """
    POST /api/chat/sessions/<session_id>/rename

    Request JSON body:
        { "title": "Thermodynamics Study Session" }

    Success (200): { "success": true, "data": {"session": {...}}, "message": "..." }
    Error (400/404): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}

    try:
        session = chat_service.rename_session(session_id, current_user.id, payload.get("title"))
        return success_response(data={"session": session.to_dict()}, message="Conversation renamed.")
    except ChatServiceError as exc:
        status = 404 if exc.error_code == "SESSION_NOT_FOUND" else 400
        return error_response(exc.message, status_code=status, error_code=exc.error_code)


@chat_api_bp.route("/sessions/<int:session_id>/bookmark", methods=["POST"])
@student_required
def api_toggle_bookmark(session_id):
    """
    POST /api/chat/sessions/<session_id>/bookmark

    Toggles the bookmark/star status of a conversation, used by the
    History and Saved Conversations pages.

    Success (200): { "success": true, "data": {"session": {...}}, "message": "..." }
    Error (404): { "success": false, "error": "...", "error_code": "SESSION_NOT_FOUND" }
    """
    try:
        session = chat_service.toggle_bookmark(session_id, current_user.id)
        message = "Conversation bookmarked." if session.is_bookmarked else "Bookmark removed."
        return success_response(data={"session": session.to_dict()}, message=message)
    except ChatServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)


@chat_api_bp.route("/sessions/<int:session_id>", methods=["DELETE"])
@student_required
def api_archive_session(session_id):
    """
    DELETE /api/chat/sessions/<session_id>

    Archives (soft-deletes) a conversation from the History page.

    Success (200): { "success": true, "message": "..." }
    Error (404): { "success": false, "error": "...", "error_code": "SESSION_NOT_FOUND" }
    """
    try:
        chat_service.archive_session(session_id, current_user.id)
        return success_response(message="Conversation deleted.")
    except ChatServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)