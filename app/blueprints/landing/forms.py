"""
forms.py (landing blueprint)

Flask-WTF form definition for the public Contact page. Kept separate
from app/blueprints/auth/forms.py since this form is used by
unauthenticated visitors and has no relationship to account
authentication.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, SubmitField
from wtforms.validators import DataRequired, Email, Length


class ContactForm(FlaskForm):
    """Form for the public Contact page (app/templates/landing/contact.html)."""

    full_name = StringField(
        "Full Name",
        validators=[DataRequired(message="Full name is required."), Length(min=2, max=120)],
    )
    email = StringField(
        "Email Address",
        validators=[DataRequired(message="Email is required."), Email(message="Enter a valid email address.")],
    )
    subject = StringField(
        "Subject",
        validators=[DataRequired(message="Subject is required."), Length(min=3, max=255)],
    )
    message = TextAreaField(
        "Message",
        validators=[DataRequired(message="Please enter a message."), Length(min=10, max=2000)],
    )
    submit = SubmitField("Send Message")