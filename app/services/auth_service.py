"""
auth_service.py

Business logic layer for authentication: student registration, login,
logout, password reset, and email verification. Kept independent of
Flask routing concerns (request parsing, JSON responses) so it can be
called from both the HTML-form blueprint (app/blueprints/auth/routes.py)
and the JSON API blueprint (app/blueprints/api/auth_api.py) without
duplicating logic.

All database writes go through SQLAlchemy against PostgreSQL via the
shared `db` session in app.extensions.
"""

from datetime import datetime, timezone
from typing import Optional, Tuple

from app.extensions import db
from app.models.user import User
from app.models.admin import Admin
from app.utils.security import (
    hash_password,
    verify_password,
    generate_secure_token,
    token_expiry_timestamp,
    is_token_expired,
)
from app.utils.validators import is_valid_email, is_strong_password, password_strength_errors
from app.utils.logger import log_to_db


class AuthError(Exception):
    """
    Raised for any expected authentication failure (duplicate email,
    invalid credentials, expired token, etc.), carrying a machine-readable
    error_code so calling blueprints can map it to the correct HTTP status
    and frontend error_code without string-matching messages.
    """

    def __init__(self, message: str, error_code: str = "AUTH_ERROR"):
        super().__init__(message)
        self.message = message
        self.error_code = error_code


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def register_student(full_name: str, email: str, password: str, confirm_password: str) -> User:
    """
    Validates and creates a new Student (User) account in PostgreSQL.

    Args:
        full_name: The student's display name.
        email: The student's email address (must be unique across "users").
        password: The plaintext password (hashed before storage).
        confirm_password: Must match `password` exactly.

    Returns:
        The newly created, persisted User instance.

    Raises:
        AuthError: If any validation rule fails or the email is already
            registered.
    """
    full_name = (full_name or "").strip()
    email = (email or "").strip().lower()

    if not full_name or len(full_name) < 2:
        raise AuthError("Full name must be at least 2 characters long.", "INVALID_NAME")

    if not is_valid_email(email):
        raise AuthError("Please provide a valid email address.", "INVALID_EMAIL")

    if password != confirm_password:
        raise AuthError("Passwords do not match.", "PASSWORD_MISMATCH")

    if not is_strong_password(password):
        errors = password_strength_errors(password)
        raise AuthError(" ".join(errors) or "Password does not meet strength requirements.", "WEAK_PASSWORD")

    existing_user = User.query.filter_by(email=email).first()
    if existing_user is not None:
        raise AuthError("An account with this email already exists.", "EMAIL_ALREADY_REGISTERED")

    new_user = User(
        full_name=full_name,
        email=email,
        password_hash=hash_password(password),
        is_email_verified=False,
        email_verification_token=generate_secure_token(),
    )

    db.session.add(new_user)
    db.session.commit()

    log_to_db(
        level="INFO",
        category="auth",
        message=f"New student account registered: {email}",
        user_id=new_user.id,
    )

    return new_user


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------
def authenticate_student(email: str, password: str) -> User:
    """
    Verifies student login credentials against PostgreSQL.

    Args:
        email: The submitted email address.
        password: The submitted plaintext password.

    Returns:
        The authenticated User instance.

    Raises:
        AuthError: If credentials are invalid or the account is deactivated.
    """
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None or not verify_password(password, user.password_hash):
        log_to_db(
            level="WARNING",
            category="security",
            message=f"Failed student login attempt for email: {email}",
        )
        raise AuthError("Invalid email or password.", "INVALID_CREDENTIALS")

    if not user.is_active:
        raise AuthError("This account has been suspended. Please contact support.", "ACCOUNT_SUSPENDED")

    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()

    log_to_db(
        level="INFO",
        category="auth",
        message=f"LOGIN: {user.full_name} ({user.email}) logged in.",
        user_id=user.id,
    )

    return user

    # user.last_login_at = datetime.now(timezone.utc)
    # db.session.commit()

    # log_to_db(level="INFO", category="auth", message=f"Student login: {email}", user_id=user.id)

    # return user


def authenticate_admin(email: str, password: str) -> Admin:
    """
    Verifies admin login credentials against PostgreSQL. Kept as a fully
    separate function (rather than a shared authenticate() with a role
    flag) to keep student and admin authentication paths independently
    auditable, per the project's privilege-separation design.

    Args:
        email: The submitted admin email address.
        password: The submitted plaintext password.

    Returns:
        The authenticated Admin instance.

    Raises:
        AuthError: If credentials are invalid or the admin account is deactivated.
    """
    email = (email or "").strip().lower()
    admin = Admin.query.filter_by(email=email).first()

    if admin is None or not verify_password(password, admin.password_hash):
        log_to_db(
            level="WARNING",
            category="security",
            message=f"Failed admin login attempt for email: {email}",
        )
        raise AuthError("Invalid email or password.", "INVALID_CREDENTIALS")

    if not admin.is_active:
        raise AuthError("This admin account has been deactivated.", "ACCOUNT_SUSPENDED")

    admin.last_login_at = datetime.now(timezone.utc)
    db.session.commit()

    log_to_db(
        level="INFO",
        category="admin_action",
        message=f"Admin login: {email}",
        admin_id=admin.id,
    )

    return admin


# ---------------------------------------------------------------------------
# Password Reset ("Forgot Password")
# ---------------------------------------------------------------------------
def request_password_reset(email: str) -> Optional[str]:
    """
    Generates and stores a password reset token for the given email, if a
    matching Student account exists. Intentionally does NOT raise an error
    (and returns None) when the email is not found, to avoid leaking which
    emails are registered (user enumeration protection).

    Args:
        email: The email address submitted on the Forgot Password page.

    Returns:
        The generated reset token if an account was found (to be emailed
        to the user by the calling route), otherwise None.
    """
    email = (email or "").strip().lower()
    user = User.query.filter_by(email=email).first()

    if user is None:
        return None

    token = generate_secure_token()
    user.password_reset_token = token
    user.password_reset_expires_at = token_expiry_timestamp(minutes=60)
    db.session.commit()

    log_to_db(
        level="INFO",
        category="auth",
        message=f"Password reset requested for: {email}",
        user_id=user.id,
    )

    return token


def reset_password(token: str, new_password: str, confirm_password: str) -> User:
    """
    Completes a password reset given a valid, non-expired token.

    Args:
        token: The reset token from the emailed link.
        new_password: The new plaintext password.
        confirm_password: Must match `new_password`.

    Returns:
        The updated User instance.

    Raises:
        AuthError: If the token is invalid/expired or the new password
            fails validation.
    """
    if new_password != confirm_password:
        raise AuthError("Passwords do not match.", "PASSWORD_MISMATCH")

    if not is_strong_password(new_password):
        errors = password_strength_errors(new_password)
        raise AuthError(" ".join(errors) or "Password does not meet strength requirements.", "WEAK_PASSWORD")

    user = User.query.filter_by(password_reset_token=token).first()

    if user is None or is_token_expired(user.password_reset_expires_at):
        raise AuthError("This password reset link is invalid or has expired.", "INVALID_OR_EXPIRED_TOKEN")

    user.password_hash = hash_password(new_password)
    user.password_reset_token = None
    user.password_reset_expires_at = None
    db.session.commit()

    log_to_db(level="INFO", category="auth", message=f"Password reset completed for: {user.email}", user_id=user.id)

    return user


# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------
def verify_email(token: str) -> User:
    """
    Marks a Student account as email-verified given a valid verification token.

    Args:
        token: The verification token from the emailed link.

    Returns:
        The updated User instance.

    Raises:
        AuthError: If no user matches the given token.
    """
    user = User.query.filter_by(email_verification_token=token).first()

    if user is None:
        raise AuthError("Invalid or already-used verification link.", "INVALID_VERIFICATION_TOKEN")

    user.is_email_verified = True
    user.email_verification_token = None
    db.session.commit()

    log_to_db(level="INFO", category="auth", message=f"Email verified for: {user.email}", user_id=user.id)

    return user


# ---------------------------------------------------------------------------
# Password Change (authenticated user changing their own password)
# ---------------------------------------------------------------------------
def change_password(user: User, current_password: str, new_password: str, confirm_password: str) -> None:
    """
    Allows an already-authenticated student to change their password from
    the Settings page, requiring re-entry of their current password.

    Args:
        user: The currently logged-in User instance.
        current_password: The user's existing plaintext password, for verification.
        new_password: The desired new plaintext password.
        confirm_password: Must match `new_password`.

    Raises:
        AuthError: If the current password is incorrect or the new
            password fails validation/confirmation checks.
    """
    if not verify_password(current_password, user.password_hash):
        raise AuthError("Current password is incorrect.", "INVALID_CURRENT_PASSWORD")

    if new_password != confirm_password:
        raise AuthError("New passwords do not match.", "PASSWORD_MISMATCH")

    if not is_strong_password(new_password):
        errors = password_strength_errors(new_password)
        raise AuthError(" ".join(errors) or "Password does not meet strength requirements.", "WEAK_PASSWORD")

    user.password_hash = hash_password(new_password)
    db.session.commit()

    log_to_db(level="INFO", category="auth", message=f"Password changed by user: {user.email}", user_id=user.id)