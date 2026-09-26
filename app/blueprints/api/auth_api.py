"""
auth_api.py

JSON REST API endpoints for authentication, consumed by the frontend's
static/js/auth.js via fetch() calls (as opposed to the server-rendered
form flow in app/blueprints/auth/routes.py). Every endpoint returns the
standardized response envelope from app/utils/responses.py.

Registered under url_prefix="/api/auth" in app/__init__.py, so full paths
are e.g. POST /api/auth/register, POST /api/auth/login, etc.
"""

from flask import Blueprint, request
from flask_login import login_user, logout_user, login_required, current_user

from app.services import auth_service
from app.services.auth_service import AuthError
from app.utils.responses import success_response, error_response
from app.utils.decorators import json_required
from app.utils.validators import is_non_empty_string
from app.extensions import limiter

auth_api_bp = Blueprint("auth_api", __name__)


@auth_api_bp.route("/register", methods=["POST"])
@limiter.limit("10 per hour")
@json_required
def api_register():
    """
    POST /api/auth/register

    Request JSON body:
        {
            "full_name": "Dhruvil_Dave",
            "email": "Dhruvil@example.com",
            "password": "SecurePass1!",
            "confirm_password": "SecurePass1!"
        }

    Success (201): { "success": true, "data": {"user": {...}}, "message": "..." }
    Error (422/409): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}

    try:
        user = auth_service.register_student(
            full_name=payload.get("full_name"),
            email=payload.get("email"),
            password=payload.get("password"),
            confirm_password=payload.get("confirm_password"),
        )
        login_user(user, remember=True)
        return success_response(
            data={"user": user.to_dict()},
            message="Account created successfully. Welcome to Minddora AI!",
            status_code=201,
        )
    except AuthError as exc:
        status = 409 if exc.error_code == "EMAIL_ALREADY_REGISTERED" else 422
        return error_response(exc.message, status_code=status, error_code=exc.error_code)

@auth_api_bp.route("/update-ai-settings", methods=["POST"])
@login_required
@json_required
def api_update_ai_settings():
    """
    POST /api/auth/update-ai-settings

    Request JSON body:
        {
            "ai_mode": "local" | "gemini",
            "gemini_api_key": "...",      // optional, only needed when switching to gemini
            "gemini_model_name": "gemini-2.0-flash"   // optional
        }

    Success (200): { "success": true, "data": {"user": {...}} }
    """
    from app.models.user import User
    from app.extensions import db

    if not isinstance(current_user, User):
        return error_response("This endpoint is for student accounts only.", status_code=403)

    payload = request.get_json(silent=True) or {}
    ai_mode = payload.get("ai_mode", "local")

    if ai_mode not in ("local", "gemini"):
        return error_response("Invalid AI mode.", status_code=400)

    current_user.ai_mode = ai_mode

    new_key = payload.get("gemini_api_key", "").strip()
    if new_key:
        current_user.gemini_api_key = new_key

    new_model = payload.get("gemini_model_name", "").strip()
    if new_model:
        current_user.gemini_model_name = new_model

    db.session.commit()

    return success_response(data={"user": current_user.to_dict()}, message="AI settings updated.")




@auth_api_bp.route("/login", methods=["POST"])
@limiter.limit("15 per hour")
@json_required
def api_login():
    """
    POST /api/auth/login

    Request JSON body:
        {
            "email": "dhruvil@example.com",
            "password": "SecurePass1!",
            "remember_me": true
        }

    Success (200): { "success": true, "data": {"user": {...}}, "message": "..." }
    Error (401/403): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")
    password = payload.get("password")
    remember_me = bool(payload.get("remember_me", False))

    if not is_non_empty_string(email) or not is_non_empty_string(password):
        return error_response("Email and password are required.", status_code=400, error_code="MISSING_FIELDS")

    try:
        user = auth_service.authenticate_student(email=email, password=password)
        login_user(user, remember=remember_me)
        return success_response(data={"user": user.to_dict()}, message=f"Welcome back, {user.full_name}!")
    except AuthError as exc:
        status = 403 if exc.error_code == "ACCOUNT_SUSPENDED" else 401
        return error_response(exc.message, status_code=status, error_code=exc.error_code)


@auth_api_bp.route("/logout", methods=["POST"])
@login_required
def api_logout():
    """
    POST /api/auth/logout

    Requires an authenticated session (student or admin).

    Success (200): { "success": true, "message": "..." }
    """
    logout_user()
    return success_response(message="You have been signed out successfully.")

@auth_api_bp.route("/update-profile", methods=["POST"])
@login_required
@json_required
def api_update_profile():
    """
    POST /api/auth/update-profile

    Requires an authenticated student session.

    Request JSON body:
        {
            "full_name": "Dhruvil Dave",
            "institution": "LDRP Institute of Technology",
            "field_of_study": "Computer Engineering"
        }

    Success (200): { "success": true, "data": {"user": {...}}, "message": "..." }
    """
    from app.models.user import User
    from app.extensions import db
    from app.utils.validators import is_non_empty_string
    from app.utils.security import sanitize_plain_text

    if not isinstance(current_user, User):
        return error_response("This endpoint is for student accounts only.", status_code=403)

    payload = request.get_json(silent=True) or {}
    full_name = payload.get("full_name", "").strip()

    if not is_non_empty_string(full_name, max_length=120):
        return error_response("Full name is required.", status_code=422, error_code="INVALID_NAME")

    current_user.full_name = sanitize_plain_text(full_name)
    current_user.institution = sanitize_plain_text(payload.get("institution", "").strip()) or None
    current_user.field_of_study = sanitize_plain_text(payload.get("field_of_study", "").strip()) or None
    db.session.commit()

    return success_response(data={"user": current_user.to_dict()}, message="Profile updated successfully.")

@auth_api_bp.route("/forgot-password", methods=["POST"])
@limiter.limit("5 per hour")
@json_required
def api_forgot_password():
    """
    POST /api/auth/forgot-password

    Request JSON body:
        { "email": "dhruvil@example.com" }

    Always returns a generic success message regardless of whether the
    email exists in PostgreSQL, to prevent user enumeration attacks.

    Success (200): { "success": true, "message": "..." }
    """
    payload = request.get_json(silent=True) or {}
    email = payload.get("email")

    if not is_non_empty_string(email):
        return error_response("Email is required.", status_code=400, error_code="MISSING_FIELDS")

    token = auth_service.request_password_reset(email)

    if token:
        # TODO (integration point): dispatch the reset email here using the
        # MAIL_* configuration values, including a link such as:
        #   f"{request.host_url}auth/reset-password/{token}"
        pass

    return success_response(
        message="If an account exists with that email, a password reset link has been sent."
    )


@auth_api_bp.route("/reset-password", methods=["POST"])
@limiter.limit("10 per hour")
@json_required
def api_reset_password():
    """
    POST /api/auth/reset-password

    Request JSON body:
        {
            "token": "the-reset-token-from-the-emailed-link",
            "new_password": "NewSecurePass1!",
            "confirm_password": "NewSecurePass1!"
        }

    Success (200): { "success": true, "message": "..." }
    Error (422): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}

    try:
        auth_service.reset_password(
            token=payload.get("token"),
            new_password=payload.get("new_password"),
            confirm_password=payload.get("confirm_password"),
        )
        return success_response(message="Your password has been reset successfully. Please sign in.")
    except AuthError as exc:
        return error_response(exc.message, status_code=422, error_code=exc.error_code)


@auth_api_bp.route("/verify-email", methods=["POST"])
@json_required
def api_verify_email():
    """
    POST /api/auth/verify-email

    Request JSON body:
        { "token": "the-verification-token-from-the-emailed-link" }

    Success (200): { "success": true, "data": {"user": {...}}, "message": "..." }
    Error (422): { "success": false, "error": "...", "error_code": "..." }
    """
    payload = request.get_json(silent=True) or {}

    try:
        user = auth_service.verify_email(payload.get("token"))
        return success_response(data={"user": user.to_dict()}, message="Your email has been verified successfully!")
    except AuthError as exc:
        return error_response(exc.message, status_code=422, error_code=exc.error_code)


@auth_api_bp.route("/change-password", methods=["POST"])
@login_required
@json_required
def api_change_password():
    """
    POST /api/auth/change-password

    Requires an authenticated student session.

    Request JSON body:
        {
            "current_password": "OldPass1!",
            "new_password": "NewSecurePass1!",
            "confirm_password": "NewSecurePass1!"
        }

    Success (200): { "success": true, "message": "..." }
    Error (401/422): { "success": false, "error": "...", "error_code": "..." }
    """
    from app.models.user import User

    if not isinstance(current_user, User):
        return error_response("This endpoint is for student accounts only.", status_code=403)

    payload = request.get_json(silent=True) or {}

    try:
        auth_service.change_password(
            user=current_user,
            current_password=payload.get("current_password"),
            new_password=payload.get("new_password"),
            confirm_password=payload.get("confirm_password"),
        )
        return success_response(message="Your password has been updated successfully.")
    except AuthError as exc:
        return error_response(exc.message, status_code=422, error_code=exc.error_code)


@auth_api_bp.route("/me", methods=["GET"])
@login_required
def api_current_user():
    """
    GET /api/auth/me

    Returns the currently authenticated user's (student or admin) profile
    data, used by the frontend on page load to hydrate the UI (e.g. show
    the correct name/avatar in the dashboard header) without a full page
    reload after login.

    Success (200): { "success": true, "data": {"user": {...}, "role": "student"|"admin"} }
    """
    from app.models.user import User
    from app.models.admin import Admin

    if isinstance(current_user, User):
        return success_response(data={"user": current_user.to_dict(), "role": "student"})
    elif isinstance(current_user, Admin):
        return success_response(data={"user": current_user.to_dict(), "role": "admin"})

    return error_response("Unknown session type.", status_code=401)