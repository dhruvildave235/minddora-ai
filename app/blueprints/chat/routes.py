"""
routes.py (chat blueprint)

Server-rendered HTML routes for the AI Chat and Search Notes pages.
These routes render the initial Jinja2 page shell; all actual chat
turns, session loading, and search queries happen via JSON API calls
from static/js/chat.js and static/js/search.js against chat_api.py and
search_api.py respectively.

All routes require an authenticated Student session and an active
(non-suspended) account.
"""

from flask import Blueprint, render_template, abort, request
from flask_login import login_required, current_user

from app.utils.decorators import student_required, active_account_required
from app.services import chat_service, document_service
from app.services.chat_service import ChatServiceError
from app.services.document_service import DocumentServiceError

chat_bp = Blueprint("chat", __name__, template_folder="../../templates")


@chat_bp.route("/chat")
@login_required
@student_required
@active_account_required
def chat_home():
    """
    Renders the main Chat page for a NEW conversation (no session_id in
    the URL). Optionally pre-scopes the conversation to a single
    document if a document_id query parameter is provided (e.g. reached
    via the "Chat with this document" button on the Document Viewer page).
    """
    document = None
    document_id = request.args.get("document_id", type=int)

    if document_id is not None:
        try:
            document = document_service.get_document_by_id(document_id, current_user.id)
        except DocumentServiceError:
            abort(404)

    # return render_template("chat/chat.html", session=None, document=document)
    return render_template("chat/chat.html", session=None, document=document, ai_mode=current_user.ai_mode)


@chat_bp.route("/chat/<int:session_id>")
@login_required
@student_required
@active_account_required
def chat_session(session_id):
    """
    Renders the Chat page for an EXISTING conversation, loading its full
    message history server-side for the initial render (subsequent
    messages in this session are sent/received via
    POST /api/chat/message).

    Args:
        session_id: The ChatSession.id to open.

    Raises:
        404: If the session is not found or not owned by the current user.
    """
    try:
        session = chat_service.get_session_with_messages(session_id, current_user.id)
    except ChatServiceError:
        abort(404)

    document = None
    if session.document_id is not None:
        try:
            document = document_service.get_document_by_id(session.document_id, current_user.id)
        except DocumentServiceError:
            document = None

    # return render_template("chat/chat.html", session=session, document=document)
    return render_template("chat/chat.html", session=session, document=document, ai_mode=current_user.ai_mode)


@chat_bp.route("/history")
@login_required
@student_required
@active_account_required
def history():
    """
    Renders the History page: a paginated list of all the student's past
    conversations. Initial page load renders the first page server-side;
    subsequent pagination/filtering is handled client-side via
    GET /api/chat/sessions.
    """
    sessions, total_count = chat_service.get_user_sessions(user_id=current_user.id, page=1, per_page=20)
    return render_template("chat/history.html", sessions=sessions, total_count=total_count, bookmarked_only=False)


@chat_bp.route("/saved-conversations")
@login_required
@student_required
@active_account_required
def saved_conversations():
    """
    Renders the Saved Conversations page: identical to History but
    restricted to bookmarked sessions only (bookmarked_only=True).
    """
    sessions, total_count = chat_service.get_user_sessions(
        user_id=current_user.id, page=1, per_page=20, bookmarked_only=True
    )
    return render_template("chat/history.html", sessions=sessions, total_count=total_count, bookmarked_only=True)


@chat_bp.route("/search")
@login_required
@student_required
@active_account_required
def search_notes_page():
    """
    Renders the Search Notes page shell: search input, mode toggle
    (semantic/keyword/hybrid), and filter controls. Actual search
    execution happens client-side via GET /api/search as the student
    types/submits a query.
    """
    return render_template("search/search.html")