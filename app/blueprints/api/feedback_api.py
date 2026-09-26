"""
feedback_api.py

JSON REST API endpoint for students to submit feedback (bug reports,
feature requests, general comments). Consumed by a feedback modal on
the student dashboard. Admin-side viewing/responding already exists in
app/blueprints/api/admin_api.py — this file only handles the student
submission path.
"""

from flask import Blueprint, request
from flask_login import current_user

from app.extensions import db, limiter
from app.models.feedback import Feedback
from app.utils.responses import success_response, error_response
from app.utils.decorators import student_required, json_required
from app.utils.validators import is_non_empty_string
from app.utils.security import sanitize_plain_text
from app.utils.logger import log_to_db

feedback_api_bp = Blueprint("feedback_api", __name__)

_VALID_CATEGORIES = {"bug", "feature_request", "general", "answer_rating"}


@feedback_api_bp.route("/submit", methods=["POST"])
@student_required
@limiter.limit("10 per hour")
@json_required
def api_submit_feedback():
    """
    POST /api/feedback/submit

    Request JSON body:
        {
            "category": "bug" | "feature_request" | "general" | "answer_rating",
            "subject": "Short subject line",
            "message": "Detailed feedback message",
            "chat_message_id": 123,   // optional, only for answer_rating
            "rating": 4                // optional, only for answer_rating
        }

    Success (201): { "success": true, "data": {"feedback": {...}}, "message": "..." }
    Error (400/422): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}

    category = payload.get("category", "general")
    subject = payload.get("subject", "")
    message = payload.get("message", "")

    if category not in _VALID_CATEGORIES:
        return error_response("Invalid feedback category.", status_code=400, error_code="INVALID_CATEGORY")

    if not is_non_empty_string(subject, max_length=255):
        return error_response("Subject is required.", status_code=422, error_code="MISSING_SUBJECT")

    if not is_non_empty_string(message, max_length=2000):
        return error_response("Message is required.", status_code=422, error_code="MISSING_MESSAGE")

    feedback_entry = Feedback(
        user_id=current_user.id,
        category=category,
        subject=sanitize_plain_text(subject),
        message=sanitize_plain_text(message),
        chat_message_id=payload.get("chat_message_id"),
        rating=payload.get("rating"),
        status="open",
    )
    db.session.add(feedback_entry)
    db.session.commit()

    log_to_db(
        level="INFO",
        category="system",
        message=f"FEEDBACK: {current_user.full_name} ({current_user.email}) submitted feedback: '{subject}'",
        user_id=current_user.id,
    )

    return success_response(
        data={"feedback": feedback_entry.to_dict()},
        message="Thank you! Your feedback has been submitted.",
        status_code=201,
    )