"""
routes.py (auth blueprint)

--------------------------------------------------------------------------
OPEN-SOURCE / LOCAL EDITION NOTE
--------------------------------------------------------------------------
There is no login system in this edition — a single local profile is
auto-created and auto-logged-in on every request (see
app/__init__.py's auto_login_local_profile). The routes below are kept
in place (rather than deleted) purely so that every existing url_for(...)
reference elsewhere in the templates/JS keeps resolving without errors;
each one simply redirects straight into the app instead of asking for
credentials. verify-email / forgot-password / reset-password are left
fully dormant — nothing links to them anymore, and they're harmless if
visited directly.
"""

from flask import Blueprint, redirect, url_for

auth_bp = Blueprint("auth", __name__, url_prefix="/auth", template_folder="../../templates/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    """Local edition: there is nothing to register — go straight to the dashboard."""
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    """Local edition: there is nothing to log into — you're always signed in as the local profile."""
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/logout")
def logout():
    """
    Local edition: there is no real session to end (the local profile is
    auto-logged-in again on the very next request), so this just sends
    you back to the dashboard rather than pretending to sign you out.
    """
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Local edition: no accounts, no passwords to reset."""
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Local edition: no accounts, no passwords to reset."""
    return redirect(url_for("dashboard.index"))


@auth_bp.route("/verify-email/<token>")
def verify_email(token):
    """Local edition: the local profile is always pre-verified."""
    return redirect(url_for("dashboard.index"))
