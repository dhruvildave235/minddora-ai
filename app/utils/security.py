"""
security.py

Security-related helper functions used across Minddora AI: password
hashing/verification (via Flask-Bcrypt), secure token generation for
email verification and password resets, and HTML sanitization to protect
against XSS in any user-supplied content that gets rendered back
(feedback messages, document titles, chat content, etc.).
"""

import secrets
import string
from datetime import datetime, timedelta, timezone

import bleach

from app.extensions import bcrypt

# ---------------------------------------------------------------------------
# Password Hashing (Flask-Bcrypt)
# ---------------------------------------------------------------------------
def hash_password(plain_password: str) -> str:
    """
    Hashes a plaintext password using bcrypt before it is stored in the
    PostgreSQL "users" or "admins" table. The plaintext password itself
    is NEVER persisted anywhere.

    Args:
        plain_password: The user-supplied plaintext password.

    Returns:
        A UTF-8 decoded bcrypt hash string, safe to store in
        User.password_hash / Admin.password_hash.
    """
    return bcrypt.generate_password_hash(plain_password).decode("utf-8")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """
    Verifies a plaintext password attempt against a stored bcrypt hash.

    Args:
        plain_password: The password submitted at login.
        password_hash: The bcrypt hash retrieved from the database.

    Returns:
        True if the password matches, False otherwise.
    """
    if not password_hash:
        return False
    return bcrypt.check_password_hash(password_hash, plain_password)


# ---------------------------------------------------------------------------
# Secure Token Generation (Email Verification / Password Reset)
# ---------------------------------------------------------------------------
def generate_secure_token(length: int = 48) -> str:
    """
    Generates a cryptographically secure, URL-safe random token used for
    email verification links and password reset links.

    Args:
        length: Number of bytes of randomness (the resulting URL-safe
            string will be longer than this due to base64-style encoding).

    Returns:
        A URL-safe random token string.
    """
    return secrets.token_urlsafe(length)


def generate_numeric_otp(digits: int = 6) -> str:
    """
    Generates a numeric one-time-passcode (e.g. for optional two-factor
    or email-verification-by-code flows).

    Args:
        digits: Number of digits in the generated OTP.

    Returns:
        A zero-padded numeric string of the requested length.
    """
    return "".join(secrets.choice(string.digits) for _ in range(digits))


def token_expiry_timestamp(minutes: int = 60) -> datetime:
    """
    Returns a timezone-aware UTC datetime representing when a generated
    token (password reset, email verification) should expire. Stored in
    User.password_reset_expires_at and checked in auth_service.py before
    honoring the token.

    Args:
        minutes: How many minutes from now the token remains valid.
    """
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


def is_token_expired(expires_at: datetime) -> bool:
    """
    Checks whether a stored expiry timestamp has already passed.

    Args:
        expires_at: The timezone-aware datetime to check, typically read
            from User.password_reset_expires_at.

    Returns:
        True if expires_at is None or is in the past, False otherwise.
    """
    if expires_at is None:
        return True
    return datetime.now(timezone.utc) > expires_at


# ---------------------------------------------------------------------------
# XSS Protection / HTML Sanitization
# ---------------------------------------------------------------------------
# Minimal allowed tag set for any user-generated content that might be
# rendered as HTML (e.g. Markdown-rendered chat messages). Raw form inputs
# like document titles, feedback subjects, and profile names should use
# sanitize_plain_text() instead, which strips ALL tags.
_ALLOWED_TAGS = [
    "p", "br", "strong", "em", "ul", "ol", "li", "code", "pre",
    "blockquote", "h1", "h2", "h3", "h4", "table", "thead", "tbody",
    "tr", "th", "td", "a",
]
_ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "target", "rel"],
}


def sanitize_html(raw_html: str) -> str:
    """
    Strips any HTML/JS not in the explicit allow-list, preventing stored
    or reflected XSS. Used when rendering AI-generated Markdown responses
    (after Markdown-to-HTML conversion) back into the Chat UI.

    Args:
        raw_html: The HTML string to sanitize.

    Returns:
        A sanitized HTML string safe to render in the browser.
    """
    if not raw_html:
        return ""
    return bleach.clean(
        raw_html,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRIBUTES,
        strip=True,
    )


def sanitize_plain_text(raw_text: str) -> str:
    """
    Strips ALL HTML tags from a plain-text input field (e.g. document
    titles, feedback subjects, profile names) to prevent stored XSS from
    fields that are never meant to contain markup at all.

    Args:
        raw_text: The raw user-submitted string.

    Returns:
        A plain-text string with all HTML tags removed.
    """
    if not raw_text:
        return ""
    return bleach.clean(raw_text, tags=[], attributes={}, strip=True).strip()