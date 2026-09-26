"""
admin_api.py

JSON REST API endpoints for the Admin Panel — consumed by
static/js/admin.js via fetch() calls. Covers user management, document
metadata oversight, feedback management, system logs, and system-wide
analytics. Every endpoint enforces admin-only access via @admin_required,
with additional fine-grained permission checks via @permission_required
where the action requires elevated privileges (e.g. modifying settings
is restricted to super_admin).

Registered under url_prefix="/api/admin" in app/__init__.py, so full
paths are e.g. GET /api/admin/users, POST /api/admin/users/<id>/suspend, etc.
"""

from flask import Blueprint, request, current_app
from flask_login import current_user

from app.extensions import limiter

from app.extensions import db
from app.models.user import User
from app.models.document import Document
from app.models.feedback import Feedback
from app.models.log import SystemLog
from app.services import analytics_service, document_service
from app.services.document_service import DocumentServiceError
from app.utils.responses import success_response, error_response, paginated_response
from app.utils.decorators import admin_required, permission_required, json_required
from app.utils.logger import log_to_db

admin_api_bp = Blueprint("admin_api", __name__)


# ---------------------------------------------------------------------------
# User Management
# ---------------------------------------------------------------------------
@admin_api_bp.route("/users", methods=["GET"])
@admin_required
@limiter.exempt

def api_list_users():
    """
    GET /api/admin/users?page=1&per_page=20&search=dhruvil

    Query params:
        page: 1-indexed page number (default 1)
        per_page: results per page (default 20, max 100)
        search: optional case-insensitive match against name/email

    Success (200): Paginated response with {"items": [...], "pagination": {...}}
    """
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    search_term = request.args.get("search", "").strip()

    query = User.query
    if search_term:
        like_pattern = f"%{search_term}%"
        query = query.filter(db.or_(User.full_name.ilike(like_pattern), User.email.ilike(like_pattern)))

    query = query.order_by(User.created_at.desc())
    total_count = query.count()
    users = query.offset((page - 1) * per_page).limit(per_page).all()

    return paginated_response(
        items=[u.to_dict() for u in users],
        page=page,
        per_page=per_page,
        total_items=total_count,
    )


@admin_api_bp.route("/users/<int:user_id>/suspend", methods=["POST"])
@admin_required
@permission_required("can_manage_users")
def api_suspend_user(user_id):
    """
    POST /api/admin/users/<user_id>/suspend

    Deactivates a student account, immediately blocking further access
    (enforced via @active_account_required on student-facing endpoints).

    Success (200): { "success": true, "data": {"user": {...}}, "message": "..." }
    Error (404): { "success": false, "error": "..." }
    """
    user = User.query.get(user_id)
    if user is None:
        return error_response("User not found.", status_code=404, error_code="USER_NOT_FOUND")

    user.is_active = False
    db.session.commit()

    log_to_db(
        level="INFO",
        category="admin_action",
        message=f"Admin suspended user account: {user.email}",
        admin_id=current_user.id,
        user_id=user.id,
    )

    return success_response(data={"user": user.to_dict()}, message="User account suspended.")

@admin_api_bp.route("/live-activity", methods=["GET"])
@admin_required
@limiter.exempt
def api_live_activity():
    """
    GET /api/admin/live-activity?since_id=123

    Returns SystemLog entries newer than since_id, for the Live Network
    visualization to animate as pulses along the matching architecture
    path. Polled frequently by the frontend, so this is exempt from rate
    limiting (mirrors the other auto-refreshed admin endpoints).
    """
    since_id = request.args.get("since_id", 0, type=int)

    logs = (
        SystemLog.query.filter(SystemLog.id > since_id)
        .order_by(SystemLog.id.asc())
        .limit(50)
        .all()
    )

    return success_response(data={
        "events": [{"id": l.id, "category": l.category, "level": l.level, "message": l.message} for l in logs],
        "latest_id": logs[-1].id if logs else since_id,
    })


@admin_api_bp.route("/users/<int:user_id>/reactivate", methods=["POST"])
@admin_required
@permission_required("can_manage_users")
def api_reactivate_user(user_id):
    """
    POST /api/admin/users/<user_id>/reactivate

    Success (200): { "success": true, "data": {"user": {...}}, "message": "..." }
    Error (404): { "success": false, "error": "..." }
    """
    user = User.query.get(user_id)
    if user is None:
        return error_response("User not found.", status_code=404, error_code="USER_NOT_FOUND")

    user.is_active = True
    db.session.commit()

    log_to_db(
        level="INFO",
        category="admin_action",
        message=f"Admin reactivated user account: {user.email}",
        admin_id=current_user.id,
        user_id=user.id,
    )

    return success_response(data={"user": user.to_dict()}, message="User account reactivated.")


@admin_api_bp.route("/users/<int:user_id>", methods=["DELETE"])
@admin_required
@permission_required("can_manage_users")
def api_delete_user(user_id):
    """
    DELETE /api/admin/users/<user_id>

    Permanently deletes a student account and all associated data
    (documents, chunks, chat sessions) via cascading foreign key
    relationships defined on the User model.

    Success (200): { "success": true, "message": "..." }
    Error (404): { "success": false, "error": "..." }
    """
    user = User.query.get(user_id)
    if user is None:
        return error_response("User not found.", status_code=404, error_code="USER_NOT_FOUND")

    user_email = user.email
    db.session.delete(user)
    db.session.commit()

    log_to_db(
        level="WARNING",
        category="admin_action",
        message=f"Admin permanently deleted user account: {user_email}",
        admin_id=current_user.id,
    )

    return success_response(message="User account permanently deleted.")


# ---------------------------------------------------------------------------
# Document Management (metadata oversight — not raw content access)
# ---------------------------------------------------------------------------
# @admin_api_bp.route("/documents", methods=["GET"])
# @admin_required
# def api_list_all_documents():
#     """
#     GET /api/admin/documents?page=1&per_page=20&status=failed

#     Query params:
#         page: 1-indexed page number (default 1)
#         per_page: results per page (default 20, max 100)
#         status: optional filter by processing_status

#     Success (200): Paginated response with {"items": [...], "pagination": {...}}

#     Note: Per Minddora AI's privacy-first design, this endpoint exposes
#     document METADATA only (filename, size, status, owner) — never chunk
#     text content — since students' uploaded material is private by default.
#     """
#     page = max(request.args.get("page", 1, type=int), 1)
#     per_page = min(request.args.get("per_page", 20, type=int), 100)
#     status_filter = request.args.get("status")

#     query = Document.query.filter_by(is_deleted=False)
#     if status_filter:
#         query = query.filter_by(processing_status=status_filter)

#     query = query.order_by(Document.uploaded_at.desc())
#     total_count = query.count()
#     documents = query.offset((page - 1) * per_page).limit(per_page).all()

#     return paginated_response(
#         items=[d.to_dict() for d in documents],
#         page=page,
#         per_page=per_page,
#         total_items=total_count,
#     )

@admin_api_bp.route("/documents", methods=["GET"])
@admin_required
@limiter.exempt

def api_list_all_documents():
    """
    GET /api/admin/documents?page=1&per_page=20&status=failed
    ...
    """
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    status_filter = request.args.get("status")

    query = Document.query.filter_by(is_deleted=False)
    if status_filter:
        query = query.filter_by(processing_status=status_filter)

    query = query.order_by(Document.uploaded_at.desc())
    total_count = query.count()
    documents = query.offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for d in documents:
        doc_dict = d.to_dict()
        owner = User.query.get(d.user_id)
        doc_dict["owner_name"] = owner.full_name if owner else "Unknown"
        doc_dict["owner_email"] = owner.email if owner else "Unknown"
        items.append(doc_dict)

    return paginated_response(
        items=items,
        page=page,
        per_page=per_page,
        total_items=total_count,
    )


@admin_api_bp.route("/documents/<int:document_id>", methods=["DELETE"])
@admin_required
@permission_required("can_manage_users")
def api_admin_delete_document(document_id):
    """
    DELETE /api/admin/documents/<document_id>

    Allows an admin to remove a document (e.g. reported for a Terms of
    Service violation), reusing document_service's deletion logic
    (including vector store cleanup) with the document's actual owner
    resolved server-side rather than trusting a client-supplied user_id.

    Success (200): { "success": true, "message": "..." }
    Error (404): { "success": false, "error": "..." }
    """
    document = Document.query.filter_by(id=document_id, is_deleted=False).first()
    if document is None:
        return error_response("Document not found.", status_code=404, error_code="DOCUMENT_NOT_FOUND")

    try:
        document_service.delete_document(document_id, document.user_id)
        log_to_db(
            level="WARNING",
            category="admin_action",
            message=f"Admin deleted document {document_id} (owner user_id={document.user_id}).",
            admin_id=current_user.id,
        )
        return success_response(message="Document deleted.")
    except DocumentServiceError as exc:
        return error_response(exc.message, status_code=404, error_code=exc.error_code)


# ---------------------------------------------------------------------------
# Feedback Management
# ---------------------------------------------------------------------------
@admin_api_bp.route("/feedback", methods=["GET"])
@admin_required
def api_list_feedback():
    """
    GET /api/admin/feedback?page=1&per_page=20&status=open&category=bug

    Success (200): Paginated response with {"items": [...], "pagination": {...}}
    """
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 20, type=int), 100)
    status_filter = request.args.get("status")
    category_filter = request.args.get("category")

    query = Feedback.query
    if status_filter:
        query = query.filter_by(status=status_filter)
    if category_filter:
        query = query.filter_by(category=category_filter)
        query = query.order_by(Feedback.created_at.desc())
    total_count = query.count()
    feedback_entries = query.offset((page - 1) * per_page).limit(per_page).all()

    items = []
    for f in feedback_entries:
        entry = f.to_dict()
        if f.user_id:
            user = User.query.get(f.user_id)
            entry["submitter_name"] = user.full_name if user else "Unknown"
            entry["submitter_email"] = user.email if user else "Unknown"
        else:
            entry["submitter_name"] = f.guest_name or "Guest"
            entry["submitter_email"] = f.guest_email or "N/A"
        items.append(entry)

    return paginated_response(
        items=items,
        page=page,
        per_page=per_page,
        total_items=total_count,
    )

    # query = query.order_by(Feedback.created_at.desc())
    # total_count = query.count()
    # feedback_entries = query.offset((page - 1) * per_page).limit(per_page).all()

    # return paginated_response(
    #     items=[f.to_dict() for f in feedback_entries],
    #     page=page,
    #     per_page=per_page,
    #     total_items=total_count,
    # )


# @admin_api_bp.route("/feedback/<int:feedback_id>/respond", methods=["POST"])
# @admin_required
# @json_required
# def api_respond_to_feedback(feedback_id):
#     """
#     POST /api/admin/feedback/<feedback_id>/respond

#     Request JSON body:
#         { "response": "Thanks for flagging this — fixed in the next release.",
#           "status": "resolved" }   // status optional, defaults to "resolved"

#     Success (200): { "success": true, "data": {"feedback": {...}}, "message": "..." }
#     Error (404): { "success": false, "error": "..." }
#     """
#     feedback_entry = Feedback.query.get(feedback_id)
#     if feedback_entry is None:
#         return error_response("Feedback entry not found.", status_code=404, error_code="FEEDBACK_NOT_FOUND")

#     payload = request.get_json(silent=True) or {}
#     response_text = payload.get("response", "")
#     new_status = payload.get("status", "resolved")

#     feedback_entry.mark_reviewed(admin_id=current_user.id, response=response_text, new_status=new_status)
#     db.session.commit()

#     return success_response(data={"feedback": feedback_entry.to_dict()}, message="Response saved.")

@admin_api_bp.route("/feedback/<int:feedback_id>/respond", methods=["POST"])
@admin_required
@json_required
def api_respond_to_feedback(feedback_id):
    """
    POST /api/admin/feedback/<feedback_id>/respond
    ...
    """
    feedback_entry = Feedback.query.get(feedback_id)
    if feedback_entry is None:
        return error_response("Feedback entry not found.", status_code=404, error_code="FEEDBACK_NOT_FOUND")

    payload = request.get_json(silent=True) or {}
    response_text = payload.get("response", "")
    new_status = payload.get("status", "resolved")

    feedback_entry.mark_reviewed(admin_id=current_user.id, response=response_text, new_status=new_status)
    db.session.commit()

    recipient_email = None
    recipient_name = None
    if feedback_entry.user_id:
        submitter = User.query.get(feedback_entry.user_id)
        if submitter:
            recipient_email = submitter.email
            recipient_name = submitter.full_name
    else:
        recipient_email = feedback_entry.guest_email
        recipient_name = feedback_entry.guest_name

    email_sent = False
    if recipient_email and response_text.strip():
        from app.services.mail_service import send_email, MailError
        try:
            send_email(
                to=recipient_email,
                subject=f"Re: {feedback_entry.subject}",
                body_html=f"""
                    <p>Hi {recipient_name or 'there'},</p>
                    <p>Thanks for reaching out to Minddora AI. Here's our response to your message:</p>
                    <p><strong>Your message:</strong> {feedback_entry.message}</p>
                    <p><strong>Our response:</strong> {response_text}</p>
                """,
            )
            email_sent = True
        except MailError as exc:
            current_app.logger.error(f"Feedback response email failed: {exc}")

    message = "Response saved and emailed to the submitter." if email_sent else "Response saved (no email sent — no email address on file)."
    return success_response(data={"feedback": feedback_entry.to_dict()}, message=message)


# ---------------------------------------------------------------------------
# System Logs
# ---------------------------------------------------------------------------
@admin_api_bp.route("/logs", methods=["GET"])
@admin_required

@limiter.exempt

@permission_required("can_view_analytics")
def api_list_logs():
    """
    GET /api/admin/logs?page=1&per_page=50&level=ERROR&category=rag_pipeline

    Success (200): Paginated response with {"items": [...], "pagination": {...}}
    """
    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 50, type=int), 200)
    level_filter = request.args.get("level")
    category_filter = request.args.get("category")

    query = SystemLog.query
    if level_filter:
        query = query.filter_by(level=level_filter.upper())
    if category_filter:
        query = query.filter_by(category=category_filter)

    query = query.order_by(SystemLog.created_at.desc())
    total_count = query.count()
    logs = query.offset((page - 1) * per_page).limit(per_page).all()

    return paginated_response(
        items=[log.to_dict() for log in logs],
        page=page,
        per_page=per_page,
        total_items=total_count,
    )


# ---------------------------------------------------------------------------
# System Analytics
# ---------------------------------------------------------------------------
@admin_api_bp.route("/analytics", methods=["GET"])
@admin_required
@permission_required("can_view_analytics")
def api_system_analytics():
    """
    GET /api/admin/analytics?days=30

    Success (200): { "success": true, "data": {...system-wide stats...} }
    """
    days = min(request.args.get("days", 30, type=int), 365)
    stats = analytics_service.get_system_analytics(days=days)
    return success_response(data=stats)

@admin_api_bp.route("/live-status-board", methods=["GET"])
@admin_required
@limiter.exempt
def api_live_status_board():
    """
    GET /api/admin/live-status-board

    Returns every student's current live status (online/offline) plus
    their most recent logged action, for the admin "office board" —
    a card-per-student view similar to a live team status dashboard.
    """
    from app.models.log import SystemLog

    students = User.query.order_by(User.full_name).all()

    cards = []
    for student in students:
        latest_log = (
            SystemLog.query.filter_by(user_id=student.id)
            .order_by(SystemLog.created_at.desc())
            .first()
        )
        cards.append({
            "id": student.id,
            "full_name": student.full_name,
            "is_online": student.is_online(),
            "is_active": student.is_active,
            "last_action": latest_log.message if latest_log else "No activity yet",
            "last_action_category": latest_log.category if latest_log else "system",
            "last_seen": student.last_seen_at.isoformat() if student.last_seen_at else None,
        })

    return success_response(data={"students": cards})