"""
routes.py (dashboard blueprint)

Server-rendered HTML routes for the student-facing dashboard area:
Dashboard home, Profile, Settings, and AI Analytics pages. These routes
render Jinja2 templates and pull data via the service layer
(document_service, chat_service, analytics_service); all mutating actions
(profile updates, password changes) are handled by the corresponding JSON
API blueprints (auth_api.py) called from the page's JavaScript, so these
routes stay read-only/rendering-focused.

All routes require an authenticated Student session (@login_required +
@student_required) and an active (non-suspended) account.
"""

from flask import Blueprint, render_template
from flask_login import login_required, current_user

from app.utils.decorators import student_required, active_account_required
from app.services import document_service, chat_service, analytics_service

dashboard_bp = Blueprint("dashboard", __name__, template_folder="../../templates/dashboard")


@dashboard_bp.route("/dashboard")
@login_required
@student_required
@active_account_required
def index():
    """
    Renders the main Dashboard home page: a summary view showing recent
    documents, recent chat activity, and quick stats (documents count,
    storage used, questions asked), giving the student an at-a-glance
    overview when they log in.
    """
    recent_documents, _ = document_service.get_user_documents(user_id=current_user.id, page=1, per_page=5)
    recent_sessions, _ = chat_service.get_user_sessions(user_id=current_user.id, page=1, per_page=5)
    quick_stats = analytics_service.get_student_analytics(user_id=current_user.id, days=7)

    return render_template(
        "dashboard/index.html",
        recent_documents=recent_documents,
        recent_sessions=recent_sessions,
        quick_stats=quick_stats,
    )


@dashboard_bp.route("/profile")
@login_required
@student_required
@active_account_required
def profile():
    """
    Renders the Profile page, showing the student's account details
    (name, email, institution, field of study, avatar) and storage usage.
    Profile edits are submitted via a JSON API call from the page's
    JavaScript (a future profile_api endpoint noted in the Future
    Features roadmap; for MVP, profile fields are edited through the
    Settings page's forms).
    """
    return render_template("dashboard/profile.html", user=current_user)


@dashboard_bp.route("/settings")
@login_required
@student_required
@active_account_required
def settings():
    """
    Renders the Settings page: account settings (change password, via
    ChangePasswordForm), notification preferences, and storage/quota
    display. Password changes are submitted via POST /api/auth/change-password.
    """
    from app.blueprints.auth.forms import ChangePasswordForm

    change_password_form = ChangePasswordForm()
    return render_template("dashboard/settings.html", user=current_user, change_password_form=change_password_form)


@dashboard_bp.route("/analytics")
@login_required
@student_required
@active_account_required
def analytics():
    """
    Renders the AI Analytics page: personal usage statistics (documents
    uploaded, questions asked, activity-over-time chart, top subjects,
    average AI answer confidence), sourced from analytics_service.
    """
    stats = analytics_service.get_student_analytics(user_id=current_user.id, days=30)
    return render_template("dashboard/analytics.html", stats=stats)


@dashboard_bp.route("/resend-verification")
@login_required
@student_required
@active_account_required
def resend_verification():
    """
    Resends the email verification link to the currently logged-in
    student's email address — used by a "Resend verification email"
    button on the Profile page for accounts that registered before
    verification emails were wired up, or who missed the original email.
    """
    from flask import flash, redirect, url_for, current_app
    from app.services.mail_service import send_email, MailError

    if current_user.is_email_verified:
        flash("Your email is already verified.", "info")
        return redirect(url_for("dashboard.profile"))

    verify_url = url_for("auth.verify_email", token=current_user.email_verification_token, _external=True)
    try:
        send_email(
            to=current_user.email,
            subject="Verify your Minddora AI email",
            body_html=f'<p><a href="{verify_url}">Click here to verify your email address</a></p>',
        )
        flash("Verification email sent. Please check your inbox.", "success")
    except MailError as exc:
        current_app.logger.error(f"Resend verification failed: {exc}")
        flash("Couldn't send the email right now. Please try again shortly.", "error")

    return redirect(url_for("dashboard.profile"))