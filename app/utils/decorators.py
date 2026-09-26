"""
decorators.py

Route decorators used across Minddora AI's blueprints.

--------------------------------------------------------------------------
OPEN-SOURCE / LOCAL EDITION NOTE
--------------------------------------------------------------------------
This is the personal, local, single-profile edition of Minddora AI: there
is no login system. A single local profile is auto-created and
auto-logged-in on every request (see app/__init__.py's
auto_login_local_profile before_request hook), so `current_user` is
always the one local profile — there is no separate Student/Admin
distinction anymore.

The decorators below are kept (rather than removed) so that every route
across the app keeps working completely unchanged — they now simply
confirm a profile is attached to the request (which, thanks to the
auto-login hook, is always true) instead of enforcing any real
authentication or role check.
"""

from functools import wraps

from flask import abort, jsonify, request
from flask_login import current_user

from app.utils.logger import log_to_db


def student_required(f):
    """
    Local edition: always passes through, since the single local profile
    is auto-logged-in on every request. Kept as a decorator (rather than
    removed from every route) so route signatures never had to change.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            # Should not normally happen (auto-login runs on every
            # request), but fail safely rather than crash if it ever does.
            wants_json = request.path.startswith("/api/")
            if wants_json:
                return jsonify({"success": False, "error": "No local profile is available."}), 401
            abort(500, description="No local profile is available.")

        return f(*args, **kwargs)

    return decorated_function


def admin_required(f):
    """
    Local edition: always passes through for the same reason as
    student_required above — there is only one local profile, and it has
    access to every page, including the admin tools (Live Network, RAG
    Visualizer, Database Browser, etc.), since this is your own machine.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            wants_json = request.path.startswith("/api/")
            if wants_json:
                return jsonify({"success": False, "error": "No local profile is available."}), 401
            abort(500, description="No local profile is available.")

        return f(*args, **kwargs)

    return decorated_function


def permission_required(permission_method_name: str):
    """
    Local edition: role-tiered admin permissions (super_admin /
    support_admin / analyst) don't apply to a single local profile —
    every admin action is available. Kept as a no-op decorator so every
    route that uses it keeps working unchanged.
    """

    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            return f(*args, **kwargs)

        return decorated_function

    return decorator


def active_account_required(f):
    """
    Ensures the local profile hasn't been marked inactive. Kept from the
    original multi-user design in case you ever want to pause the app's
    own access to itself; harmless no-op in normal local use since the
    local profile is always created active.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not getattr(current_user, "is_active", True):
            return jsonify({
                "success": False,
                "error": "This local profile has been marked inactive.",
            }), 403
        return f(*args, **kwargs)

    return decorated_function


def json_required(f):
    """
    Ensures the incoming request has a JSON body (Content-Type:
    application/json) before the route handler attempts request.get_json().

    Returns:
        400 JSON error if the request does not contain valid JSON.
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not request.is_json:
            return jsonify({"success": False, "error": "Request body must be JSON."}), 400
        return f(*args, **kwargs)

    return decorated_function
