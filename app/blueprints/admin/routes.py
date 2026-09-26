"""
routes.py (admin blueprint)

Server-rendered HTML routes for the Admin Panel: Admin Login, Admin
Dashboard, User Management, Document Management, Feedback Management,
System Logs, and System Analytics pages. Login uses a traditional form
POST (AdminLoginForm); all other pages render a page shell whose data
tables/charts are populated client-side via the JSON endpoints in
app/blueprints/api/admin_api.py, keeping these routes rendering-focused.

All routes except /admin/login require an authenticated Admin session
via @admin_required. Fine-grained permission checks (e.g. settings access
restricted to super_admin) are enforced again at the API layer in
admin_api.py — these page routes only gate on "is this an admin at all,"
with individual page sections hiding/disabling controls client-side
based on the role returned by GET /api/auth/me.
"""

from flask import Blueprint, render_template, redirect, url_for
from flask_login import current_user

from app.services import analytics_service
from app.utils.decorators import admin_required

admin_bp = Blueprint("admin", __name__, template_folder="../../templates/admin")


@admin_bp.route("/login", methods=["GET", "POST"])
def login():
    """
    Local edition: there is no separate admin account — the single local
    profile already has full access to every admin page. This route is
    kept only so url_for("admin.login") still resolves anywhere it's
    referenced; it just sends you straight to the Admin Dashboard.
    """
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/logout")
def logout():
    """
    Local edition: nothing to sign out of — the local profile stays
    logged in. Kept only so url_for("admin.logout") still resolves.
    """
    return redirect(url_for("admin.dashboard"))


@admin_bp.route("/dashboard")
@admin_required
def dashboard():
    """
    Renders the Admin Dashboard: a summary view showing key platform
    metrics (total users, documents, questions asked, open feedback
    count, recent error count) for a quick health-check on login.
    """
    stats = analytics_service.get_system_analytics(days=7)
    return render_template("admin/dashboard.html", stats=stats)

@admin_bp.route("/database")
@admin_required
def database():
    """Renders the Database browser page shell (password gate + table grid)."""
    return render_template("admin/database.html")


@admin_bp.route("/users")
@admin_required
def users():
    """
    Renders the User Management page shell: a searchable, paginated
    table of all student accounts with suspend/reactivate/delete
    actions, populated client-side via GET /api/admin/users.
    """
    return render_template("admin/users.html")


@admin_bp.route("/documents")
@admin_required
def documents():
    """
    Renders the Document Management page shell: a paginated table of all
    uploaded documents platform-wide (metadata only — never chunk text
    content, per Minddora AI's privacy-first design), populated
    client-side via GET /api/admin/documents.
    """
    return render_template("admin/documents.html")


@admin_bp.route("/feedback")
@admin_required
def feedback():
    """
    Renders the Feedback Management page shell: a filterable table of
    student-submitted feedback with an inline response/status-update
    action, populated client-side via GET /api/admin/feedback.
    """
    return render_template("admin/feedback.html")


@admin_bp.route("/logs")
@admin_required
def logs():
    """
    Renders the Error Logs / System Logs page shell: a filterable,
    paginated table of SystemLog entries (by level and category),
    populated client-side via GET /api/admin/logs.
    """
    return render_template("admin/logs.html")


@admin_bp.route("/analytics")
@admin_required
def analytics():
    """
    Renders the System Analytics page: platform-wide usage charts
    (signups over time, questions over time, storage usage, vector
    store size). The selected date range is read from a ?days= query
    parameter (defaulting to 30) so it survives a full page reload when
    the student changes the dropdown.
    """
    from flask import request

    days = request.args.get("days", 30, type=int)
    if days not in (7, 30, 90, 365):
        days = 30

    stats = analytics_service.get_system_analytics(days=days)
    return render_template("admin/analytics.html", stats=stats, selected_days=days)


@admin_bp.route("/network")
@admin_required
def network():
    """Renders the Live Network visualization page."""
    return render_template("admin/network.html")


@admin_bp.route("/rag-visualizer")
@admin_required
def rag_visualizer():
    """Renders the RAG Visualizer page."""
    from app.models.document import Document
    documents = Document.query.filter_by(is_deleted=False, processing_status="ready").all()
    return render_template("admin/rag_visualizer.html", documents=documents)