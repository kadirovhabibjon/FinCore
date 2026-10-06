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


async def test_the_contact_change_notice_says_what_changed_and_what_to_do(
    smtp: list[EmailMessage],
) -> None:
    await mailer.send_contact_changed(
        to="old@example.com", first_name="Aziza", what="email address"
    )

    [message] = smtp
    assert message["To"] == "old@example.com"
    assert message["Subject"] == "Your FinCore email address was changed"
    body = message.get_content()
    assert "If you did not" in body and "change your password" in body


async def test_the_new_device_email_names_the_device_and_says_what_to_do(
    smtp: list[EmailMessage],
) -> None:
    await mailer.send_new_device(
        to="aziza@example.com",
        first_name="Aziza",
        device="Safari on iPhone",
        ip_address="203.0.113.7",
    )

    [message] = smtp
    assert message["Subject"] == "New sign-in to your FinCore account"
    body = " ".join(message.get_content().split())
    assert "from Safari on iPhone (IP address 203.0.113.7)" in body
    assert "change your password" in body


@pytest.mark.parametrize(
    ("address", "deliverable"),
    [
        ("aziza@gmail.com", True),
        ("someone@mail.uz", True),
        ("e2e-1234@example.com", False),
        ("x@sub.example.org", False),
        ("x@EXAMPLE.NET", False),
        ("x@anything.test", False),
        ("x@nowhere.invalid", False),
        ("not-an-address", True),  # no "@": the whole string is the domain; SMTP rejects it
        ("x@", False),
    ],
)
def test_reserved_test_domains_are_never_mailed(address: str, deliverable: bool) -> None:
    assert mailer.is_deliverable(address) is deliverable


def test_nothing_is_handed_to_the_mail_server_for_a_test_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    opened: list[str] = []
    monkeypatch.setattr(mailer.smtplib, "SMTP", lambda *args, **kwargs: opened.append("smtp"))
    message = EmailMessage()
    message["To"] = "e2e-1234@example.com"

    mailer._send(message)

    assert opened == []


def test_configured_means_a_host_is_set(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    assert not mailer.is_configured()
    monkeypatch.setattr(settings, "smtp_host", "smtp.gmail.com")
    assert mailer.is_configured()
