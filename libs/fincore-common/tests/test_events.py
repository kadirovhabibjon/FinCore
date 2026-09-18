from uuid import UUID

from fincore_common.events import EventEnvelope, EventType


def test_envelope_fills_in_event_id_version_and_timestamp_by_default() -> None:
    envelope = EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED, producer="payment-service", data={"foo": "bar"}
    )

    assert isinstance(envelope.event_id, UUID)
    assert envelope.event_version == 1
    assert envelope.occurred_at is not None
    assert envelope.correlation_id is None


def test_envelope_round_trips_through_json() -> None:
    original = EventEnvelope(
        event_type=EventType.TRANSFER_FAILED,
        producer="payment-service",
        correlation_id="corr-1",
        data={"transfer_id": "abc-123", "reason": "insufficient funds"},
    )

    restored = EventEnvelope.model_validate_json(original.model_dump_json())

    assert restored == original
    assert restored.event_type is EventType.TRANSFER_FAILED
