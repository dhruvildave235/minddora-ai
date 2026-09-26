"""
search_api.py

JSON REST API endpoint for the standalone "Search Notes" page — consumed
by the frontend's static/js/search.js via fetch() calls. Wraps
search_service.search_notes(), exposing search mode selection
(semantic/keyword/hybrid) and filtering by document, subject, and date
range as query parameters. Enforces student-only access via
@student_required.

Registered under url_prefix="/api/search" in app/__init__.py, so the full
path is GET /api/search.
"""

from datetime import datetime

from flask import Blueprint, request
from flask_login import current_user

from app.services import search_service
from app.services.search_service import SearchServiceError
from app.utils.responses import success_response, error_response
from app.utils.decorators import student_required
from app.extensions import limiter

search_api_bp = Blueprint("search_api", __name__)


@search_api_bp.route("", methods=["GET"])
@student_required
@limiter.limit("60 per hour")
def api_search_notes():
    """
    GET /api/search?q=thermodynamics&mode=hybrid&document_id=7&subject=Physics&date_from=2026-01-01&date_to=2026-07-01

    Query params:
        q: the search query string (required)
        mode: "semantic" | "keyword" | "hybrid" (default "hybrid")
        document_id: optional int, restrict to a single document
        subject: optional exact-match subject/category filter
        date_from: optional ISO date string (YYYY-MM-DD), lower bound on upload date
        date_to: optional ISO date string (YYYY-MM-DD), upper bound on upload date
        top_k: optional int, max results to return (default 15, max 50)

    Success (200): { "success": true, "data": {"results": [...], "count": int} }
    Error (400): { "success": false, "error": "...", "error_code": "..." }
    """
    query_text = request.args.get("q", "").strip()
    if not query_text:
        return error_response("Please provide a search query using the 'q' parameter.", status_code=400, error_code="MISSING_QUERY")

    mode = request.args.get("mode", "hybrid").lower()
    document_id = request.args.get("document_id", type=int)
    subject_filter = request.args.get("subject")
    top_k = min(request.args.get("top_k", 15, type=int), 50)

    date_from = _parse_date_param(request.args.get("date_from"))
    date_to = _parse_date_param(request.args.get("date_to"))

    try:
        results = search_service.search_notes(
            user_id=current_user.id,
            query_text=query_text,
            mode=mode,
            document_id=document_id,
            subject_filter=subject_filter,
            date_from=date_from,
            date_to=date_to,
            top_k=top_k,
        )
        return success_response(data={"results": results, "count": len(results)})
    except SearchServiceError as exc:
        return error_response(exc.message, status_code=400, error_code=exc.error_code)


def _parse_date_param(date_string: str):
    """
    Parses an optional 'YYYY-MM-DD' query parameter into a datetime
    object for use as a date_from/date_to filter bound.

    Args:
        date_string: The raw query parameter value, or None if not provided.

    Returns:
        A datetime object, or None if date_string was not provided or
        could not be parsed (invalid dates are silently ignored rather
        than raising an error, so a malformed date filter degrades to
        "no filter" instead of failing the whole search request).
    """
    if not date_string:
        return None
    try:
        return datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        return None