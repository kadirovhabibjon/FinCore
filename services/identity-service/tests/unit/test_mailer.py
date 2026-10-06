import smtplib
from email.message import EmailMessage

import pytest

from app.core.config import settings
from app.services import mailer


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> list[EmailMessage]:
    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(settings, "smtp_username", "fincore@example.com")
    monkeypatch.setattr(settings, "smtp_password", "app-password")
    monkeypatch.setattr(settings, "smtp_from", "")
    sent: list[EmailMessage] = []
    monkeypatch.setattr(mailer, "_send", sent.append)
    return sent


async def test_the_email_carries_the_code_and_says_what_to_do_with_it(
    smtp: list[EmailMessage],
) -> None:
    await mailer.send_reset_code(to="aziza@example.com", first_name="Aziza", code="493817")

    [message] = smtp
    assert message["To"] == "aziza@example.com"
    assert message["From"] == "fincore@example.com"  # falls back to the username
    assert "reset code" in message["Subject"] and "493817" not in message["Subject"]
    body = message.get_content()
    assert "493817" in body and "Hello Aziza" in body
    assert "10 minutes" in body
    assert "did not ask" in body and "Never share" in body


async def test_a_mail_server_failure_is_logged_without_the_code_or_address(
    monkeypatch: pytest.MonkeyPatch, smtp: list[EmailMessage]
) -> None:
    def refuse(message: EmailMessage) -> None:
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials for aziza@example.com")

    logged: list[str] = []
    monkeypatch.setattr(mailer, "_send", refuse)
    monkeypatch.setattr(
        mailer.logger, "error", lambda message, *args: logged.append(message % args)
    )

    # Never raises: it runs after the response has already gone out.
    await mailer.send_reset_code(to="aziza@example.com", first_name="Aziza", code="493817")

    [line] = logged
    assert "SMTPAuthenticationError" in line
    assert "493817" not in line and "aziza@example.com" not in line


def test_configured_means_a_host_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    assert not mailer.is_configured()
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    assert mailer.is_configured()
