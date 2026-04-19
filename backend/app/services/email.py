"""Email service for sending messages via Gmail SMTP."""

import asyncio
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from functools import partial

from app.config import get_settings

logger = logging.getLogger(__name__)


def _send_smtp(smtp_host: str, smtp_email: str, smtp_password: str, to_email: str, msg: str) -> None:
    """Blocking SMTP send — meant to run in a thread pool."""
    with smtplib.SMTP_SSL(smtp_host, 465, timeout=10) as server:
        server.login(smtp_email, smtp_password)
        server.sendmail(smtp_email, to_email, msg)


async def send_password_reset_email(to_email: str, reset_token: str) -> None:
    """Send a password reset email with a link containing the JWT token.

    If SMTP is not configured, logs the reset link instead of sending.
    SMTP I/O runs in a thread pool to avoid blocking the event loop.
    """
    settings = get_settings()

    reset_url = f"{settings.frontend_url}/reset-password?token={reset_token}"

    if not settings.smtp_email or not settings.smtp_password:
        logger.warning(
            "SMTP not configured — reset link logged instead of sent. "
            "Set SMTP_EMAIL and SMTP_PASSWORD in .env"
        )
        logger.info("Password reset link: %s", reset_url)
        return

    subject = "Password reset — UniRAG"
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 500px; margin: 0 auto;">
        <h2>Password reset</h2>
        <p>You received this email because someone requested a password reset for your account.</p>
        <p>Click the button below to set a new password:</p>
        <p style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background-color: #2563eb; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; font-weight: bold;">
                Reset password
            </a>
        </p>
        <p style="color: #6b7280; font-size: 14px;">
            This link is valid for {settings.password_reset_expire_minutes} minutes.
        </p>
        <p style="color: #6b7280; font-size: 14px;">
            If you did not request a password reset, simply ignore this email.
        </p>
        <hr style="border: none; border-top: 1px solid #e5e7eb; margin: 20px 0;">
        <p style="color: #9ca3af; font-size: 12px;">UniRAG — University Knowledge System</p>
    </div>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_email
    msg["To"] = to_email
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None,
        partial(_send_smtp, settings.smtp_host, settings.smtp_email, settings.smtp_password, to_email, msg.as_string()),
    )
    logger.info("Password reset email sent successfully")
