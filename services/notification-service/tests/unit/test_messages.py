import uuid

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.messages import (
    UnhandledEventTypeError,
    compose_messages,
    compose_transfer_message,
)

_USER_ID = uuid.uuid4()


def _envelope(event_type: EventType, **data_overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-ABC123",
        "initiator_user_id": str(_USER_ID),
        "amount_minor": 150_00,
        "currency": "UZS",
        "status": "COMPLETED",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(data_overrides)
    return EventEnvelope(event_type=event_type, producer="payment-service", data=data)


def test_composes_a_completed_transfer_message() -> None:
    recipient, subject, body = compose_transfer_message(_envelope(EventType.TRANSFER_COMPLETED))

    assert recipient == _USER_ID
    assert subject == "Transfer completed"
    assert "TRF-ABC123" in body
    assert "150.00 UZS" in body


def test_composes_a_failed_transfer_message_with_the_reason() -> None:
    envelope = _envelope(EventType.TRANSFER_FAILED, failure_reason="insufficient funds")

    recipient, subject, body = compose_transfer_message(envelope)

    assert subject == "Transfer failed"
    assert "insufficient funds" in body


def test_a_failed_transfer_without_a_reason_still_composes_a_message() -> None:
    envelope = _envelope(EventType.TRANSFER_FAILED, failure_reason=None)

    _, _, body = compose_transfer_message(envelope)

    assert "an internal error" in body


def test_rejects_an_event_type_it_does_not_know_how_to_compose() -> None:
    """`EventType` only has two members today, but this guards against a
    silent no-op if a third one is ever added to the registry without
    teaching this function about it.
    """
    envelope = _envelope(EventType.TRANSFER_COMPLETED)
    envelope.event_type = "some.other.event"  # type: ignore[assignment]

    with pytest.raises(UnhandledEventTypeError):
        compose_transfer_message(envelope)


def test_a_completed_transfer_tells_the_sender_and_the_recipient_by_name() -> None:
    recipient = uuid.uuid4()
    envelope = _envelope(
        EventType.TRANSFER_COMPLETED,
        recipient_user_id=str(recipient),
        sender_name="Aziza K.",
        recipient_name="Bobur T.",
        amount_minor=1_250_000_00,
    )

    to_sender, to_recipient = compose_messages(envelope)

    assert to_sender.recipient_user_id == _USER_ID
    assert to_sender.notification_type == "transfer.completed"
    assert to_sender.body == "You sent 1,250,000.00 UZS to Bobur T. — reference TRF-ABC123"
    assert to_recipient.recipient_user_id == recipient
    assert to_recipient.notification_type == "transfer.received"
    assert to_recipient.subject == "Money received"
    assert to_recipient.body == "Aziza K. sent you 1,250,000.00 UZS."


def test_without_names_the_messages_still_read_properly() -> None:
    envelope = _envelope(EventType.TRANSFER_COMPLETED, recipient_user_id=str(uuid.uuid4()))

    to_sender, to_recipient = compose_messages(envelope)

    assert to_sender.body == "Your transfer TRF-ABC123 of 150.00 UZS completed successfully."
    assert to_recipient.body == "You received 150.00 UZS."


def test_only_the_sender_hears_about_a_failed_transfer_or_an_unknown_recipient() -> None:
    failed = _envelope(
        EventType.TRANSFER_FAILED,
        recipient_user_id=str(uuid.uuid4()),
        recipient_name="Bobur T.",
        failure_reason="Insufficient Funds",
    )
    # An event published before recipients were recorded.
    old = _envelope(EventType.TRANSFER_COMPLETED)

    [to_sender] = compose_messages(failed)
    assert to_sender.body == (
        "Your transfer TRF-ABC123 of 150.00 UZS to Bobur T. failed: Insufficient Funds."
    )
    assert len(compose_messages(old)) == 1
