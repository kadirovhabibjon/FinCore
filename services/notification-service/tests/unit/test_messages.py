import uuid

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.messages import UnhandledEventTypeError, compose_transfer_message

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
