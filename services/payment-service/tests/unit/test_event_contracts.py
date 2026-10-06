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
from app.services.transfers import transfer_outbox_event
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
    row = transfer_outbox_event(
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
    row = transfer_outbox_event(
        _transfer(), EventType.TRANSFER_COMPLETED, status=TransferStatus.COMPLETED
    )
    wire = _on_the_wire(row)
    wire["data"]["internal_note"] = "leaked"

    with pytest.raises(AssertionError, match="internal_note"):
        assert_valid_event(wire)


@pytest.mark.parametrize(
    ("event_type", "status", "with_names"),
    [
        (EventType.MONEY_REQUEST_CREATED, "PENDING", True),
        (EventType.MONEY_REQUEST_CREATED, "PENDING", False),
        (EventType.MONEY_REQUEST_DECLINED, "DECLINED", True),
    ],
)
def test_money_request_events_match_their_contract(
    event_type: EventType, status: str, with_names: bool
) -> None:
    from app.domain.money_request import MoneyRequest, MoneyRequestStatus
    from app.services.money_requests import _event

    request = MoneyRequest(
        id=uuid.uuid4(),
        reference="REQ-CONTRACT01",
        requester_user_id=uuid.uuid4(),
        requester_wallet_id=uuid.uuid4(),
        payer_user_id=uuid.uuid4(),
        requester_name="Aziza K." if with_names else None,
        payer_name="Bobur T." if with_names else None,
        amount_minor=50_000,
        currency="UZS",
        note="Dinner" if with_names else None,
    )

    assert_valid_event(_on_the_wire(_event(request, event_type, MoneyRequestStatus(status))))


@pytest.mark.parametrize(
    ("event_type", "status", "reason"),
    [
        (EventType.EXCHANGE_COMPLETED, "COMPLETED", None),
        (EventType.EXCHANGE_FAILED, "FAILED", "Insufficient Funds"),
        (EventType.EXCHANGE_FAILED, "FAILED", None),
    ],
)
def test_exchange_events_match_their_contract(
    event_type: EventType, status: str, reason: str | None
) -> None:
    from decimal import Decimal

    from app.domain.exchange import Exchange, ExchangeStatus
    from app.services.exchanges import _event

    exchange = Exchange(
        id=uuid.uuid4(),
        reference="EXC-CONTRACT01",
        initiator_user_id=uuid.uuid4(),
        source_wallet_id=uuid.uuid4(),
        destination_wallet_id=uuid.uuid4(),
        source_position_account_id=uuid.uuid4(),
        destination_position_account_id=uuid.uuid4(),
        source_amount_minor=1_200_000_00,
        source_currency="UZS",
        destination_amount_minor=100_00,
        destination_currency="USD",
        # A rate small enough to tempt Decimal into exponent notation.
        rate=Decimal("1") / Decimal("11835.853217"),
        failure_reason=reason,
    )

    wire = _on_the_wire(_event(exchange, event_type, ExchangeStatus(status)))

    assert_valid_event(wire)
    assert "E" not in wire["data"]["rate"].upper()
