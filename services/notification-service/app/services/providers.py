import logging
from typing import Protocol
from uuid import UUID

logger = logging.getLogger(__name__)


class ProviderUnavailableError(Exception):
    """The kind of failure a real provider (an SMTP relay, a Twilio
    call) can raise that has nothing to do with the message itself — a
    timeout, a 5xx, a dropped connection. Retrying later has a real
    chance of succeeding, unlike a malformed event (spec Section 16's
    "timeout -> retry" vs. "validation error -> DLT immediately";
    app/services/retry.py's classifier treats this type, specifically,
    as retryable).
    """


class NotificationProvider(Protocol):
    """A delivery channel (spec Section 15: "Email / SMS / Push").
    Every provider here is a logging mock for v1 — no paid external
    provider is required by the spec — but the interface is what lets a
    real one (e.g. an SMTP client, a Twilio client) replace a mock later
    without touching app/services/consumer.py.
    """

    channel: str

    async def send(self, *, recipient_user_id: UUID, subject: str, body: str) -> None: ...


class LoggingProvider:
    """Logs what would have been sent instead of actually sending it —
    acceptable for local development per spec Section 15, and easy to
    assert against in tests (caplog) without a real mail/SMS/push
    provider or its credentials.
    """

    def __init__(self, channel: str) -> None:
        self.channel = channel

    async def send(self, *, recipient_user_id: UUID, subject: str, body: str) -> None:
        logger.info(
            "notification dispatched",
            extra={
                "channel": self.channel,
                "recipient_user_id": str(recipient_user_id),
                "subject": subject,
            },
        )


def default_providers() -> list[NotificationProvider]:
    return [LoggingProvider("EMAIL"), LoggingProvider("SMS"), LoggingProvider("PUSH")]
