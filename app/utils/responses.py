"""
responses.py

Standardized JSON response helpers used across all Minddora AI API
blueprints (auth, documents, chat, search, admin). Ensures every API
endpoint returns a consistent response envelope shape, which the
frontend JavaScript (static/js/*.js) relies on for uniform success/error
handling instead of parsing ad-hoc response shapes per endpoint.

Standard success envelope:
    {
        "success": true,
        "data": { ... },
        "message": "Optional human-readable message"
    }

Standard error envelope:
    {
        "success": false,
        "error": "Human-readable error message",
        "error_code": "OPTIONAL_MACHINE_READABLE_CODE",
        "details": { ... }   # optional, e.g. field-level validation errors
    }
"""

from typing import Any, Optional

from flask import jsonify


def success_response(data: Any = None, message: str = None, status_code: int = 200):
    """
    Builds a standardized success JSON response.

    Args:
        data: The payload to return (dict, list, or JSON-serializable value).
        message: Optional human-readable success message for UI toasts.
        status_code: HTTP status code, defaults to 200 OK.

    Returns:
        A Flask (Response, status_code) tuple ready to be returned from a route.
    """
    payload = {"success": True}
    if data is not None:
        payload["data"] = data
    if message is not None:
        payload["message"] = message
    return jsonify(payload), status_code


def error_response(
    error: str,
    status_code: int = 400,
    error_code: Optional[str] = None,
    details: Optional[dict] = None,
):
    """
    Builds a standardized error JSON response.

    Args:
        error: Human-readable error message shown to the user/logged by
            the frontend toast/notification system.
        status_code: HTTP status code (400 Bad Request, 401 Unauthorized,
            403 Forbidden, 404 Not Found, 409 Conflict, 422 Unprocessable
            Entity, 429 Too Many Requests, 500 Internal Server Error, etc.).
        error_code: Optional machine-readable code (e.g. "INVALID_CREDENTIALS",
            "STORAGE_QUOTA_EXCEEDED") the frontend can branch on without
            string-matching the human-readable message.
        details: Optional dict of extra structured error info, commonly
            field-level validation errors, e.g. {"email": "Invalid format"}.

    Returns:
        A Flask (Response, status_code) tuple ready to be returned from a route.
    """
    payload = {"success": False, "error": error}
    if error_code is not None:
        payload["error_code"] = error_code
    if details is not None:
        payload["details"] = details
    return jsonify(payload), status_code


def paginated_response(
    items: list,
    page: int,
    per_page: int,
    total_items: int,
    message: str = None,
):
    """
    Builds a standardized paginated success response, used by list
    endpoints (documents list, chat sessions list, admin user list,
    system logs list) that query PostgreSQL with LIMIT/OFFSET pagination.

    Args:
        items: The list of already-serialized items for the current page.
        page: The current page number (1-indexed).
        per_page: Number of items requested per page.
        total_items: Total number of matching items across all pages,
            typically from a separate COUNT(*) query.
        message: Optional human-readable message.

    Returns:
        A Flask (Response, status_code) tuple ready to be returned from a route.
    """
    total_pages = (total_items + per_page - 1) // per_page if per_page else 0
    data = {
        "items": items,
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total_items": total_items,
            "total_pages": total_pages,
            "has_next": page < total_pages,
            "has_prev": page > 1,
        },
    }
    return success_response(data=data, message=message)


def validation_error_response(field_errors: dict):
    """
    Builds a standardized 422 response specifically for form/input
    validation failures, where multiple fields may each have their own
    error message (e.g. registration form with invalid email AND weak
    password submitted together).

    Args:
        field_errors: Dict mapping field name -> error message(s), e.g.
            {"email": "Invalid email format.", "password": ["Too short.", "Missing digit."]}

    Returns:
        A Flask (Response, status_code) tuple with status 422.
    """
    return error_response(
        error="One or more fields failed validation.",
        status_code=422,
        error_code="VALIDATION_ERROR",
        details=field_errors,
    )