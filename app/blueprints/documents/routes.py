"""
routes.py (documents blueprint)

Server-rendered HTML routes for the document management pages: Upload
Notes, My Documents, and Document Viewer. These routes render Jinja2
templates; the actual upload/list/delete/reprocess actions are performed
via JSON API calls from the page's JavaScript (static/js/upload.js)
against app/blueprints/api/document_api.py, keeping these routes
read-only/rendering-focused.

All routes require an authenticated Student session and an active
(non-suspended) account.
"""

from flask import Blueprint, render_template, abort
from flask_login import login_required, current_user

from app.utils.decorators import student_required, active_account_required
from app.services import document_service
from app.services.document_service import DocumentServiceError

documents_bp = Blueprint("documents", __name__, template_folder="../../templates/documents")


@documents_bp.route("/upload")
@login_required
@student_required
@active_account_required
def upload():
    """
    Renders the Upload Notes page: drag-and-drop upload zone, file
    validation feedback, and progress indicators, all driven by
    static/js/upload.js calling POST /api/documents/upload.
    """
    return render_template("documents/upload.html")


@documents_bp.route("/my-documents")
@login_required
@student_required
@active_account_required
def my_documents():
    """
    Renders the My Documents page: a paginated, filterable list of the
    student's uploaded documents with processing status, subject
    filters, and actions (view, delete, retry, chat-with-this-document).
    The initial page load renders the first page server-side; subsequent
    pagination/filtering is handled client-side via GET /api/documents.
    """
    documents, total_count = document_service.get_user_documents(user_id=current_user.id, page=1, per_page=20)
    return render_template("documents/my_documents.html", documents=documents, total_count=total_count)


@documents_bp.route("/document/<int:document_id>")
@login_required
@student_required
@active_account_required
def viewer(document_id):
    """
    Renders the Document Viewer page for a single document: metadata,
    processing status, and (if ready) a "Chat with this document" entry
    point that starts a new document-scoped ChatSession.

    Args:
        document_id: The Document.id to view.

    Raises:
        404: If the document is not found or not owned by the current user.
    """
    try:
        document = document_service.get_document_by_id(document_id, current_user.id)
    except DocumentServiceError:
        abort(404)

    return render_template("documents/viewer.html", document=document)