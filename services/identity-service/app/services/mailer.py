"""Outgoing email, for the one thing identity-service ever mails: a
password-reset code. Plain SMTP with STARTTLS from the standard library,
run in a worker thread so a slow mail server never blocks the event loop.
"""

import asyncio
import logging
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def is_configured() -> bool:
    return bool(settings.smtp_host)


def _send(message: EmailMessage) -> None:
    context = ssl.create_default_context()
    with smtplib.SMTP(
        settings.smtp_host, settings.smtp_port, timeout=settings.smtp_timeout_seconds
    ) as smtp:
        smtp.starttls(context=context)
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)


async def send_reset_code(*, to: str, first_name: str, code: str) -> None:
    """Emails the code. Called in the background after the response has
    gone out, so it never raises: a failure is logged (without the code
    or the address) and the customer can ask for another code."""
    minutes = settings.password_reset_code_ttl_seconds // 60
    message = EmailMessage()
    message["Subject"] = "Your FinCore password reset code"
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to
    message.set_content(
        f"Hello {first_name},\n\n"
        f"Your FinCore password reset code is: {code}\n\n"
        f"It works once and expires in {minutes} minutes. Enter it on the "
        "password reset page together with your new password.\n\n"
        "If you did not ask to reset your password, ignore this email: your "
        "password has not changed. Never share this code with anyone - FinCore "
        "staff will never ask for it.\n"
    )
    try:
        await asyncio.to_thread(_send, message)
    except Exception as exc:
        logger.error("password reset email could not be sent: %s", type(exc).__name__)


async def send_contact_changed(*, to: str, first_name: str, what: str) -> None:
    """Tells the account's previous email address that its email address
    or phone number (`what`) was changed, so an owner who didn't do it
    finds out. Like the reset email, sent in the background and never
    raises."""
    message = EmailMessage()
    message["Subject"] = f"Your FinCore {what} was changed"
    message["From"] = settings.smtp_from or settings.smtp_username
    message["To"] = to
    message.set_content(
        f"Hello {first_name},\n\n"
        f"The {what} on your FinCore account was just changed, after the "
        "account's password was entered.\n\n"
        "If you did this, there is nothing to do.\n\n"
        "If you did not, someone else knows your password: sign in, change "
        "your password in Account, and check the email address and phone "
        "number shown there.\n"
    )
    try:
        await asyncio.to_thread(_send, message)
    except Exception as exc:
        logger.error("contact change email could not be sent: %s", type(exc).__name__)
