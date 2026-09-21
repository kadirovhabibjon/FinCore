import uuid

import pytest
from fincore_common import EventEnvelope, EventType

from app.services.consumer import MalformedEventError, handle_domain_event


def _transfer_envelope(**overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-AUDIT001",
        "initiator_user_id": str(uuid.uuid4()),
        "amount_minor": 500_00,
        "currency": "UZS",
        "status": "COMPLETED",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED,
        producer="payment-service",
        correlation_id="corr-audit-1",
        data=data,
    )


def _payment_envelope(**overrides: object) -> EventEnvelope:
    data = {
        "payment_id": str(uuid.uuid4()),
        "reference": "PAY-AUDIT001",
        "initiator_user_id": str(uuid.uuid4()),
        "merchant_id": str(uuid.uuid4()),
        "amount_minor": 250_00,
        "currency": "UZS",
        "status": "SUCCESS",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return EventEnvelope(
        event_type=EventType.PAYMENT_COMPLETED,
        producer="payment-service",
        correlation_id="corr-audit-2",
        data=data,
    )


def test_transfer_completed_maps_to_an_audit_log_with_the_spec_example_action_name() -> None:
    envelope = _transfer_envelope()

    audit_log = handle_domain_event(envelope)

    assert audit_log.event_id == envelope.event_id
    assert audit_log.action == "TRANSFER_COMPLETED"
    assert audit_log.resource_type == "Transfer"
    assert audit_log.resource_id == envelope.data["transfer_id"]
    assert audit_log.actor_id == uuid.UUID(envelope.data["initiator_user_id"])
    assert audit_log.result == "COMPLETED"
    assert audit_log.correlation_id == "corr-audit-1"
    assert audit_log.occurred_at == envelope.occurred_at
    # Lifted fields don't also appear duplicated in `details`.
    assert "transfer_id" not in audit_log.details
    assert "initiator_user_id" not in audit_log.details
    assert audit_log.details["amount_minor"] == 500_00


def test_payment_failed_maps_correctly() -> None:
    base = _payment_envelope()
    envelope = EventEnvelope(
        event_type=EventType.PAYMENT_FAILED,
        producer="payment-service",
        data={**base.data, "status": "FAILED", "failure_reason": "insufficient funds"},
    )

    audit_log = handle_domain_event(envelope)

    assert audit_log.action == "PAYMENT_FAILED"
    assert audit_log.resource_type == "Payment"
    assert audit_log.resource_id == envelope.data["payment_id"]
    assert audit_log.result == "FAILED"
    assert audit_log.details["failure_reason"] == "insufficient funds"
    assert audit_log.details["merchant_id"] == envelope.data["merchant_id"]


def test_missing_resource_id_raises_malformed_event_error() -> None:
    envelope = _transfer_envelope()
    del envelope.data["transfer_id"]

    with pytest.raises(MalformedEventError):
        handle_domain_event(envelope)


def test_missing_status_raises_malformed_event_error() -> None:
    envelope = _transfer_envelope()
    del envelope.data["status"]

    with pytest.raises(MalformedEventError):
        handle_domain_event(envelope)


def test_actor_id_is_none_when_not_present_rather_than_raising() -> None:
    envelope = _transfer_envelope(initiator_user_id=None)

    audit_log = handle_domain_event(envelope)

    assert audit_log.actor_id is None
