"""
validators.py

Shared input and file validation utilities used across Minddora AI's
services and blueprints (auth, document upload, chat, feedback). Keeping
these as pure, framework-agnostic functions makes them easy to unit test
and reuse from both Flask routes and background processing services.
"""

import os
import re
import hashlib
from typing import Optional

from werkzeug.datastructures import FileStorage

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")

# Minimum 8 characters, at least one uppercase, one lowercase, one digit,
# one special character — enforced at registration and password reset.
PASSWORD_REGEX = re.compile(
    r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[!@#$%^&*(),.?\":{}|<>]).{8,}$"
)

ALLOWED_EXTENSIONS = {"pdf", "docx", "txt", "md", "png", "jpg", "jpeg"}
MAX_FILENAME_LENGTH = 255


# ---------------------------------------------------------------------------
# Email / Password Validation
# ---------------------------------------------------------------------------
def is_valid_email(email: str) -> bool:
    """Returns True if the given string is a syntactically valid email address."""
    if not email or len(email) > 255:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def is_strong_password(password: str) -> bool:
    """
    Returns True if the password meets Minddora AI's strength policy:
    minimum 8 characters, with at least one uppercase letter, one lowercase
    letter, one digit, and one special character.
    """
    if not password:
        return False
    return bool(PASSWORD_REGEX.match(password))


def password_strength_errors(password: str) -> list:
    """
    Returns a list of human-readable error messages describing which
    password policy rules were violated, for display in registration/
    password-reset form validation feedback.
    """
    errors = []
    if not password or len(password) < 8:
        errors.append("Password must be at least 8 characters long.")
    if not re.search(r"[A-Z]", password or ""):
        errors.append("Password must contain at least one uppercase letter.")
    if not re.search(r"[a-z]", password or ""):
        errors.append("Password must contain at least one lowercase letter.")
    if not re.search(r"\d", password or ""):
        errors.append("Password must contain at least one digit.")
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password or ""):
        errors.append("Password must contain at least one special character.")
    return errors


# ---------------------------------------------------------------------------
# File Validation
# ---------------------------------------------------------------------------
def get_file_extension(filename: str) -> str:
    """Returns the lowercase file extension (without the dot) of a filename."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def is_allowed_file_extension(filename: str, allowed: set = None) -> bool:
    """
    Returns True if the filename's extension is present in the allowed set.

    Args:
        filename: The original uploaded filename.
        allowed: Optional override of allowed extensions; defaults to
            Minddora AI's global ALLOWED_EXTENSIONS set.
    """
    allowed = allowed or ALLOWED_EXTENSIONS
    return get_file_extension(filename) in allowed


def is_valid_filename_length(filename: str) -> bool:
    """Returns True if the filename does not exceed the maximum allowed length."""
    return bool(filename) and len(filename) <= MAX_FILENAME_LENGTH


def validate_upload_file(file: FileStorage, max_size_bytes: int) -> Optional[str]:
    """
    Runs a full validation pass on an uploaded file before it is persisted
    to disk or queued for the RAG ingestion pipeline.

    Args:
        file: The Werkzeug FileStorage object from the multipart upload.
        max_size_bytes: Maximum allowed file size, sourced from
            app.config["MAX_CONTENT_LENGTH"].

    Returns:
        None if the file passes all checks, otherwise a human-readable
        error message describing the first validation failure encountered.
    """
    if file is None or file.filename == "":
        return "No file was selected for upload."

    if not is_valid_filename_length(file.filename):
        return f"Filename exceeds the maximum length of {MAX_FILENAME_LENGTH} characters."

    if not is_allowed_file_extension(file.filename):
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        return f"Unsupported file type. Allowed types: {allowed_list}."

    # Determine actual size by seeking to the end of the stream, then
    # resetting the pointer so the caller can still read/save the file.
    file.stream.seek(0, os.SEEK_END)
    file_size = file.stream.tell()
    file.stream.seek(0)

    if file_size == 0:
        return "The uploaded file is empty."

    if file_size > max_size_bytes:
        max_mb = max_size_bytes / (1024 * 1024)
        return f"File exceeds the maximum allowed size of {max_mb:.0f} MB."

    return None


def compute_file_hash(file: FileStorage) -> str:
    """
    Computes the SHA-256 hash of an uploaded file's contents, used for
    duplicate-detection against a user's existing documents before the
    file is persisted or processed by the RAG pipeline.

    Args:
        file: The Werkzeug FileStorage object. The stream is fully read
            and then reset to position 0 so subsequent code can still
            save the file to disk.

    Returns:
        A 64-character lowercase hex digest string.
    """
    file.stream.seek(0)
    sha256 = hashlib.sha256()
    for chunk in iter(lambda: file.stream.read(8192), b""):
        sha256.update(chunk)
    file.stream.seek(0)
    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# General Input Sanitization Helpers
# ---------------------------------------------------------------------------
def is_non_empty_string(value: str, max_length: int = None) -> bool:
    """Returns True if value is a non-empty, non-whitespace-only string within an optional max length."""
    if not value or not value.strip():
        return False
    if max_length is not None and len(value) > max_length:
        return False
    return True


def is_valid_rating(rating) -> bool:
    """Returns True if rating is an integer between 1 and 5 inclusive (used for Feedback.rating)."""
    try:
        rating_int = int(rating)
    except (TypeError, ValueError):
        return False
    return 1 <= rating_int <= 5



