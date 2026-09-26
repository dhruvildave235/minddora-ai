"""
forms.py (auth blueprint)

Flask-WTF form definitions for all authentication-related HTML pages:
Register, Login, Forgot Password, and Reset Password. These forms power
server-rendered template submissions (app/templates/auth/*.html) and
provide CSRF protection automatically via Flask-WTF's integration with
the app-wide CSRFProtect extension (app.extensions.csrf).

Note: The JSON API blueprint (app/blueprints/api/auth_api.py) does NOT
use these WTForms classes — it validates raw JSON payloads directly via
app/utils/validators.py, since API clients (JS fetch calls, future mobile
apps) submit JSON rather than form-encoded data. These forms exist
specifically for the traditional server-rendered form flow.
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired, Email, EqualTo, Length, ValidationError

from app.models.user import User
from app.utils.validators import is_strong_password


class RegisterForm(FlaskForm):
    """Form for the Student Register page (app/templates/auth/register.html)."""

    full_name = StringField(
        "Full Name",
        validators=[DataRequired(message="Full name is required."), Length(min=2, max=120)],
    )
    email = StringField(
        "Email Address",
        validators=[DataRequired(message="Email is required."), Email(message="Enter a valid email address.")],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required."), Length(min=8, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(message="Please confirm your password."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    agree_to_terms = BooleanField(
        "I agree to the Terms of Service and Privacy Policy",
        validators=[DataRequired(message="You must agree to the terms to register.")],
    )
    submit = SubmitField("Create Account")

    def validate_email(self, field):
        """
        Custom validator checking, against PostgreSQL, that the email is
        not already registered — runs in addition to the AuthError check
        in auth_service.py, giving inline field-level feedback in the
        rendered HTML form before the request even reaches the service layer.
        """
        existing = User.query.filter_by(email=field.data.strip().lower()).first()
        if existing is not None:
            raise ValidationError("An account with this email already exists.")

    def validate_password(self, field):
        """Enforces Minddora AI's password strength policy at the form level."""
        if not is_strong_password(field.data):
            raise ValidationError(
                "Password must be at least 8 characters and include an uppercase letter, "
                "lowercase letter, digit, and special character."
            )


class LoginForm(FlaskForm):
    """Form for the Student Login page (app/templates/auth/login.html)."""

    email = StringField(
        "Email Address",
        validators=[DataRequired(message="Email is required."), Email(message="Enter a valid email address.")],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required.")],
    )
    remember_me = BooleanField("Keep me signed in")
    submit = SubmitField("Sign In")


class AdminLoginForm(FlaskForm):
    """Form for the separate Admin Login page (app/templates/admin/login.html)."""

    email = StringField(
        "Admin Email",
        validators=[DataRequired(message="Email is required."), Email(message="Enter a valid email address.")],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired(message="Password is required.")],
    )
    submit = SubmitField("Sign In to Admin Panel")


class ForgotPasswordForm(FlaskForm):
    """Form for the Forgot Password page (app/templates/auth/forgot_password.html)."""

    email = StringField(
        "Email Address",
        validators=[DataRequired(message="Email is required."), Email(message="Enter a valid email address.")],
    )
    submit = SubmitField("Send Reset Link")


class ResetPasswordForm(FlaskForm):
    """
    Form for the "set new password" page a user lands on after clicking
    their emailed reset link (token is passed via the URL, not this form).
    """

    password = PasswordField(
        "New Password",
        validators=[DataRequired(message="Password is required."), Length(min=8, max=128)],
    )
    confirm_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(message="Please confirm your new password."),
            EqualTo("password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Reset Password")

    def validate_password(self, field):
        """Enforces Minddora AI's password strength policy at the form level."""
        if not is_strong_password(field.data):
            raise ValidationError(
                "Password must be at least 8 characters and include an uppercase letter, "
                "lowercase letter, digit, and special character."
            )


class ChangePasswordForm(FlaskForm):
    """Form for the authenticated Settings page's change-password section."""

    current_password = PasswordField(
        "Current Password",
        validators=[DataRequired(message="Current password is required.")],
    )
    new_password = PasswordField(
        "New Password",
        validators=[DataRequired(message="New password is required."), Length(min=8, max=128)],
    )
    confirm_new_password = PasswordField(
        "Confirm New Password",
        validators=[
            DataRequired(message="Please confirm your new password."),
            EqualTo("new_password", message="Passwords must match."),
        ],
    )
    submit = SubmitField("Update Password")

    def validate_new_password(self, field):
        """Enforces Minddora AI's password strength policy at the form level."""
        if not is_strong_password(field.data):
            raise ValidationError(
                "Password must be at least 8 characters and include an uppercase letter, "
                "lowercase letter, digit, and special character."
            )