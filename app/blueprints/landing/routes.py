"""
routes.py (landing blueprint)

Server-rendered HTML routes for Minddora AI's public marketing pages:
Landing (home), About, Features, Pricing, and Contact. These pages are
publicly accessible without authentication and contain no dynamic,
per-user data — they are static marketing content rendered via Jinja2
templates, with calls-to-action linking into the auth blueprint's
Register/Login pages.
"""

from flask import Blueprint, render_template, redirect, url_for, flash

from app.blueprints.landing.forms import ContactForm

landing_bp = Blueprint("landing", __name__, template_folder="../../templates/landing")


@landing_bp.route("/")
def index():
    """Renders the public Landing Page — Minddora AI's marketing homepage."""
    return render_template("landing/index.html")

@landing_bp.route("/terms")
def terms():
    """Renders the Terms of Service page."""
    return render_template("landing/terms.html")


@landing_bp.route("/privacy")
def privacy():
    """Renders the Privacy Policy page."""
    return render_template("landing/privacy.html")


@landing_bp.route("/about")
def about():
    """Renders the About page: mission, story, and team information."""
    return render_template("landing/about.html")


@landing_bp.route("/features")
def features():
    """Renders the Features page: a detailed breakdown of Minddora AI's capabilities."""
    return render_template("landing/features.html")


@landing_bp.route("/pricing")
def pricing():
    """Renders the (optional) Pricing page, showing available plans/tiers."""
    return render_template("landing/pricing.html")


@landing_bp.route("/contact", methods=["GET", "POST"])
def contact():
    """
    ...
    """
    from app.extensions import db
    from app.models.feedback import Feedback
    #from app.utils.validators import sanitize_plain_text
    from app.utils.security import sanitize_plain_text

    form = ContactForm()

    if form.validate_on_submit():
        feedback_entry = Feedback(
            user_id=None,
            guest_name=sanitize_plain_text(form.full_name.data),
            guest_email=sanitize_plain_text(form.email.data),
            category="general",
            subject=sanitize_plain_text(form.subject.data),
            message=sanitize_plain_text(form.message.data),
            status="open",
        )
        db.session.add(feedback_entry)
        db.session.commit()

        flash("Thanks for reaching out! Our team will get back to you soon.", "success")
        return redirect(url_for("landing.contact"))

    return render_template("landing/contact.html", form=form)

# @landing_bp.route("/contact", methods=["GET", "POST"])
# def contact():
#     """
#     Renders and processes the Contact page's inquiry form.

#     POST: Validates the form and persists the inquiry (via a lightweight
#     ContactInquiry record — noted for implementation alongside Feedback
#     in a future iteration; for MVP this simply flashes a confirmation
#     message without a dedicated storage table, since contact-page
#     inquiries are pre-registration and not tied to a User account).
#     """
#     form = ContactForm()

#     if form.validate_on_submit():
#         # TODO (integration point): persist the inquiry or forward it via
#         # email using the MAIL_* configuration values.
#         flash("Thanks for reaching out! Our team will get back to you soon.", "success")
#         return redirect(url_for("landing.contact"))

#     return render_template("landing/contact.html", form=form)