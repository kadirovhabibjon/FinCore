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


async def test_a_completed_transfer_notifies_both_people_once_each() -> None:
    sender, recipient = uuid.uuid4(), uuid.uuid4()
    provider = _RecordingProvider("PUSH")
    envelope = _envelope(sender, recipient_user_id=str(recipient), sender_name="Aziza K.")

    await handle_transfer_event(envelope, [provider])
    await handle_transfer_event(envelope, [provider])  # redelivered

    notifications = await _notifications_for_event(envelope.event_id)
    assert {n.recipient_user_id: n.notification_type for n in notifications} == {
        sender: "transfer.completed",
        recipient: "transfer.received",
    }
    assert all(n.read_at is None for n in notifications)
    assert [call[0] for call in provider.calls] == [sender, recipient]


async def test_a_retry_after_a_partial_failure_only_tells_whoever_was_missed() -> None:
    """The provider fails on the recipient's message after the sender's
    went out: the retry must not tell the sender a second time."""
    sender, recipient = uuid.uuid4(), uuid.uuid4()
    envelope = _envelope(sender, recipient_user_id=str(recipient))

    class _FailsFor(_RecordingProvider):
        fail_for: uuid.UUID | None = recipient

        async def send(self, *, recipient_user_id: uuid.UUID, subject: str, body: str) -> None:
            if recipient_user_id == self.fail_for:
                raise RuntimeError("provider down")
            await super().send(recipient_user_id=recipient_user_id, subject=subject, body=body)

    provider = _FailsFor("PUSH")
    with pytest.raises(RuntimeError):
        await handle_transfer_event(envelope, [provider])
    provider.fail_for = None
    await handle_transfer_event(envelope, [provider])

    assert [call[0] for call in provider.calls] == [sender, recipient]
    assert len(await _notifications_for_event(envelope.event_id)) == 2
