"""
mail_service.py

Sends transactional emails (password reset, email verification) via
SMTP. Uses Gmail's free SMTP relay by default — no paid email service
required. Requires a Gmail "App Password" (not your regular Gmail
password) since Google blocks plain password SMTP login for security.

Setup (free):
    1. Enable 2-Step Verification on your Google account.
    2. Go to https://myaccount.google.com/apppasswords
    3. Generate an app password for "Mail".
    4. Put that 16-character password in .env as MAIL_PASSWORD.
"""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from flask import current_app


class MailError(Exception):
    """Raised when sending an email fails."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def send_email(to: str, subject: str, body_html: str) -> None:
    """
    Sends an HTML email via SMTP using the app's configured mail settings.

    Args:
        to: Recipient email address.
        subject: Email subject line.
        body_html: HTML content of the email body.

    Raises:
        MailError: If sending fails for any reason (bad credentials,
            network issue, etc.). Callers should catch this and degrade
            gracefully (e.g. still show "reset link sent" to avoid user
            enumeration, but log the real failure).
    """
    mail_server = current_app.config["MAIL_SERVER"]
    mail_port = current_app.config["MAIL_PORT"]
    mail_username = current_app.config["MAIL_USERNAME"]
    mail_password = current_app.config["MAIL_PASSWORD"]
    mail_sender = current_app.config["MAIL_DEFAULT_SENDER"]

    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = mail_sender
    message["To"] = to
    message.attach(MIMEText(body_html, "html"))

    try:
        with smtplib.SMTP(mail_server, mail_port) as server:
            server.starttls()
            server.login(mail_username, mail_password)
            server.sendmail(mail_sender, to, message.as_string())
    except Exception as exc:  # noqa: BLE001
        raise MailError(f"Failed to send email: {exc}") from exc