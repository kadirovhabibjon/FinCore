import uuid

import pytest
from fincore_common import EventEnvelope, EventType
from sqlalchemy import select

from app.db import session as db_session
from app.domain.notification import Notification
from app.services.consumer import handle_transfer_event

pytestmark = pytest.mark.usefixtures("migrated_database")


class _RecordingProvider:
    def __init__(self, channel: str) -> None:
        self.channel = channel
        self.calls: list[tuple[uuid.UUID, str, str]] = []

    async def send(self, *, recipient_user_id: uuid.UUID, subject: str, body: str) -> None:
        self.calls.append((recipient_user_id, subject, body))


def _envelope(user_id: uuid.UUID, **overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-XYZ789",
        "initiator_user_id": str(user_id),
        "amount_minor": 500_00,
        "currency": "UZS",
        "status": "COMPLETED",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED, producer="payment-service", data=data
    )


async def _notifications_for_event(event_id: uuid.UUID) -> list[Notification]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(Notification).where(Notification.event_id == event_id)
        )
        return list(result.scalars().all())


async def test_handling_an_event_dispatches_to_every_provider_and_records_it() -> None:
    user_id = uuid.uuid4()
    providers = [_RecordingProvider("EMAIL"), _RecordingProvider("SMS")]
    envelope = _envelope(user_id)

    await handle_transfer_event(envelope, providers)

    for provider in providers:
        assert len(provider.calls) == 1
        assert provider.calls[0][0] == user_id
        assert provider.calls[0][1] == "Transfer completed"

    rows = await _notifications_for_event(envelope.event_id)
    assert len(rows) == 1
    assert rows[0].recipient_user_id == user_id
    assert rows[0].notification_type == "transfer.completed"


async def test_handling_the_same_event_id_twice_only_notifies_once() -> None:
    """The whole point of `Notification.event_id` being UNIQUE (spec
    Section 14.3): redelivery of the same event — the normal
    consequence of at-least-once delivery — must not double-notify a
    user.
    """
    user_id = uuid.uuid4()
    providers = [_RecordingProvider("EMAIL")]
    envelope = _envelope(user_id)

    await handle_transfer_event(envelope, providers)
    await handle_transfer_event(envelope, providers)

    assert len(providers[0].calls) == 1
    rows = await _notifications_for_event(envelope.event_id)
    assert len(rows) == 1
