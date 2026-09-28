"""Producer side of contracts/events: every (event type, status)
combination payment-service can emit is built through the same helper
the real code path uses and serialized exactly as the outbox relay puts
it on the wire (app/services/outbox.py), then validated against the
committed JSON Schema. A payload change that isn't mirrored in
contracts/events/ fails here, before any consumer ever sees it.
"""

import uuid
from datetime import UTC, datetime

import pytest
from fincore_common import EventEnvelope, EventType

from app.domain.outbox import OutboxEvent
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.services.payments import payment_outbox_event
from app.services.transfers import _transfer_outbox_event
from tests.contracts import assert_valid_event


def _on_the_wire(row: OutboxEvent) -> dict:
    """Mirrors relay_outbox_events' own envelope construction."""
    envelope = EventEnvelope(
        event_id=uuid.uuid4(),
        event_type=EventType(row.event_type),
        producer="payment-service",
        correlation_id=row.correlation_id,
        data=row.payload,
    )
    return envelope.model_dump(mode="json")


def _transfer() -> Transfer:
    return Transfer(
        id=uuid.uuid4(),
        reference="TRF-CONTRACT01",
        initiator_user_id=uuid.uuid4(),
        source_wallet_id=uuid.uuid4(),
        destination_wallet_id=uuid.uuid4(),
        amount_minor=25_000,
        currency="UZS",
    )


def _payment() -> Payment:
    return Payment(
        id=uuid.uuid4(),
        reference="PAY-CONTRACT01",
        initiator_user_id=uuid.uuid4(),
        source_wallet_id=uuid.uuid4(),
        merchant_id=uuid.uuid4(),
        amount_minor=12_000,
        currency="UZS",
    )


_NOW = datetime.now(UTC)


@pytest.mark.parametrize(
    ("event_type", "status", "failure_reason", "completed_at"),
    [
        (EventType.TRANSFER_COMPLETED, TransferStatus.COMPLETED, None, _NOW),
        (EventType.TRANSFER_FAILED, TransferStatus.FAILED, "blocked by fraud check", None),
    ],
)
def test_transfer_events_match_their_contract(
    event_type: EventType,
    status: TransferStatus,
    failure_reason: str | None,
    completed_at: datetime | None,
) -> None:
    row = _transfer_outbox_event(
        _transfer(),
        event_type,
        status=status,
        failure_reason=failure_reason,
        completed_at=completed_at,
    )

    assert_valid_event(_on_the_wire(row))


@pytest.mark.parametrize(
    ("event_type", "status", "failure_reason", "completed_at"),
    [
        (EventType.PAYMENT_COMPLETED, PaymentStatus.SUCCESS, None, _NOW),
        (EventType.PAYMENT_FAILED, PaymentStatus.FAILED, "insufficient funds", None),
        (EventType.PAYMENT_FAILED, PaymentStatus.EXPIRED, "expired awaiting review", None),
        (EventType.PAYMENT_REFUNDED, PaymentStatus.PARTIALLY_REFUNDED, None, _NOW),
        (EventType.PAYMENT_REFUNDED, PaymentStatus.REFUNDED, None, _NOW),
    ],
)
def test_payment_events_match_their_contract(
    event_type: EventType,
    status: PaymentStatus,
    failure_reason: str | None,
    completed_at: datetime | None,
) -> None:
    row = payment_outbox_event(
        _payment(),
        event_type,
        status=status,
        failure_reason=failure_reason,
        completed_at=completed_at,
    )

    assert_valid_event(_on_the_wire(row))


def test_a_payload_the_contract_does_not_allow_is_caught() -> None:
    """Guards the guard: an extra, unreviewed field must fail."""
    row = _transfer_outbox_event(
        _transfer(), EventType.TRANSFER_COMPLETED, status=TransferStatus.COMPLETED
    )
    wire = _on_the_wire(row)
    wire["data"]["internal_note"] = "leaked"

    with pytest.raises(AssertionError, match="internal_note"):
        assert_valid_event(wire)
