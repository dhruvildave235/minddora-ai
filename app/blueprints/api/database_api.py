"""
database_api.py

Read-only-by-default database browser for the Admin Panel's "Database"
tab. Lets an admin view any table's rows in a generated grid and delete
individual rows, without writing raw SQL. Requires a fresh password
re-entry (separate from the admin's login session) before any table
data can be viewed, since this view exposes raw row data across every
table in the system.

Generic by design: table structure is read directly from each
SQLAlchemy model's __table__.columns, so adding a new model later
requires only adding it to TABLE_REGISTRY below — no new route needed.
"""

from datetime import datetime, timezone, timedelta

from flask import Blueprint, request, session
from flask_login import current_user

from app.extensions import db
from app.models.user import User
from app.models.admin import Admin
from app.models.document import Document
from app.models.chunk import Chunk
from app.models.chat import ChatSession, ChatMessage
from app.models.feedback import Feedback
from app.models.log import SystemLog
from app.utils.responses import success_response, error_response, paginated_response
from app.utils.decorators import admin_required, json_required
from app.utils.security import verify_password
from app.utils.logger import log_to_db

database_api_bp = Blueprint("database_api", __name__)

# ---------------------------------------------------------------------------
# Table registry — maps a URL-safe table name to its SQLAlchemy model.
# Add a new model here to make it browsable; no other code changes needed.
# ---------------------------------------------------------------------------
TABLE_REGISTRY = {
    "users": User,
    "admins": Admin,
    "documents": Document,
    "chunks": Chunk,
    "chat_sessions": ChatSession,
    "chat_messages": ChatMessage,
    "feedback": Feedback,
    "system_logs": SystemLog,
}

# Columns never shown in the browser, regardless of table, since they hold
# security-sensitive values that have no legitimate reason to be displayed.
SENSITIVE_COLUMNS = {"password_hash", "email_verification_token", "password_reset_token"}

UNLOCK_DURATION_MINUTES = 15


def _is_unlocked() -> bool:
    """Checks whether this admin session has a still-valid database unlock."""
    unlocked_at = session.get("db_unlocked_at")
    if not unlocked_at:
        return False
    unlocked_time = datetime.fromisoformat(unlocked_at)
    return (datetime.now(timezone.utc) - unlocked_time) < timedelta(minutes=UNLOCK_DURATION_MINUTES)


def _serialize_row(instance) -> dict:
    """
    Converts any SQLAlchemy model instance into a JSON-safe dict by
    reading its table's actual columns, skipping sensitive fields.
    Generic across every table in TABLE_REGISTRY — no per-model code.
    """
    result = {}
    for col in instance.__table__.columns:
        if col.name in SENSITIVE_COLUMNS:
            continue
        value = getattr(instance, col.name)
        if isinstance(value, datetime):
            value = value.isoformat()
        elif isinstance(value, bytes):
            value = "<binary>"
        result[col.name] = value
    return result


# @database_api_bp.route("/unlock", methods=["POST"])
# @admin_required
# @json_required
# def api_unlock_database():
#     """
#     POST /api/admin/database/unlock

#     Re-verifies the currently logged-in admin's password before granting
#     access to the Database tab for this session, for the next 15 minutes.

#     Request JSON body: { "password": "..." }
#     Success (200): { "success": true, "message": "..." }
#     Error (401): wrong password
#     """
#     payload = request.get_json(silent=True) or {}
#     password = payload.get("password", "")

#     if not verify_password(password, current_user.password_hash):
#         log_to_db(
#             level="WARNING",
#             category="security",
#             message=f"Failed database-unlock attempt by admin: {current_user.email}",
#             admin_id=current_user.id,
#         )
#         return error_response("Incorrect password.", status_code=401, error_code="INVALID_PASSWORD")

@database_api_bp.route("/unlock", methods=["POST"])
@admin_required
@json_required
def api_unlock_database():
    """
    POST /api/admin/database/unlock
    ...
    """
    import hmac
    from flask import current_app

    payload = request.get_json(silent=True) or {}
    password = payload.get("password", "")

    correct_password = current_app.config["DB_PANEL_PASSWORD"]

    if not hmac.compare_digest(password, correct_password):
        log_to_db(
            level="WARNING",
            category="security",
            message=f"Failed database-unlock attempt by admin: {current_user.email}",
            admin_id=current_user.id,
        )
        return error_response("Incorrect password.", status_code=401, error_code="INVALID_PASSWORD")
    
    session["db_unlocked_at"] = datetime.now(timezone.utc).isoformat()

    log_to_db(
        level="INFO",
        category="admin_action",
        message=f"Admin {current_user.email} unlocked the database browser.",
        admin_id=current_user.id,
    )

    return success_response(message="Database view unlocked.")


@database_api_bp.route("/tables", methods=["GET"])
@admin_required
def api_list_tables():
    """
    GET /api/admin/database/tables

    Returns every browsable table with its row count. Requires an
    active unlock (see /unlock above).

    Success (200): { "success": true, "data": {"tables": [...]} }
    Error (403): unlock expired or was never granted
    """
    if not _is_unlocked():
        return error_response("Database view is locked. Please re-enter your password.", status_code=403, error_code="DB_LOCKED")

    tables = []
    for table_name, model in TABLE_REGISTRY.items():
        tables.append({
            "name": table_name,
            "row_count": model.query.count(),
            "column_count": len(model.__table__.columns),
        })

    return success_response(data={"tables": tables})


@database_api_bp.route("/tables/<table_name>", methods=["GET"])
@admin_required
def api_view_table(table_name):
    """
    GET /api/admin/database/tables/<table_name>?page=1&per_page=20

    Returns a page of rows from the given table, with column names for
    the frontend to render a generic grid.

    Success (200): { "success": true, "data": {"columns": [...], "items": [...], "pagination": {...}} }
    Error (403/404)
    """
    if not _is_unlocked():
        return error_response("Database view is locked. Please re-enter your password.", status_code=403, error_code="DB_LOCKED")

    model = TABLE_REGISTRY.get(table_name)
    if model is None:
        return error_response("Unknown table.", status_code=404, error_code="TABLE_NOT_FOUND")

    page = max(request.args.get("page", 1, type=int), 1)
    per_page = min(request.args.get("per_page", 20, type=int), 100)

    query = model.query.order_by(model.id.desc())
    total_count = query.count()
    rows = query.offset((page - 1) * per_page).limit(per_page).all()

    columns = [col.name for col in model.__table__.columns if col.name not in SENSITIVE_COLUMNS]
    items = [_serialize_row(r) for r in rows]

    data = paginated_response(items=items, page=page, per_page=per_page, total_items=total_count)
    # paginated_response already returns a Flask response; rebuild with columns included instead
    return success_response(data={
        "columns": columns,
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_count,
            "total_pages": (total_count + per_page - 1) // per_page if per_page else 0,
        },
    })


@database_api_bp.route("/tables/<table_name>/<int:row_id>", methods=["DELETE"])
@admin_required
def api_delete_row(table_name, row_id):
    """
    DELETE /api/admin/database/tables/<table_name>/<row_id>

    Deletes a single row by its primary key. Cascading foreign key
    relationships (already defined on the models) handle cleanup of
    dependent rows automatically.

    Success (200): { "success": true, "message": "..." }
    Error (403/404)
    """
    if not _is_unlocked():
        return error_response("Database view is locked. Please re-enter your password.", status_code=403, error_code="DB_LOCKED")

    model = TABLE_REGISTRY.get(table_name)
    if model is None:
        return error_response("Unknown table.", status_code=404, error_code="TABLE_NOT_FOUND")

    instance = model.query.get(row_id)
    if instance is None:
        return error_response("Row not found.", status_code=404, error_code="ROW_NOT_FOUND")

    db.session.delete(instance)
    db.session.commit()

    log_to_db(
        level="WARNING",
        category="admin_action",
        message=f"Admin {current_user.email} deleted row {row_id} from table '{table_name}'.",
        admin_id=current_user.id,
    )

    return success_response(message=f"Row deleted from {table_name}.")