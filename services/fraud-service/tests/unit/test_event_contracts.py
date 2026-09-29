"""Producer side of contracts/events for fraud-service: the event for
each decision is built through the same helper the real code path uses
(app/services/outbox.py) and validated against its committed schema.
"""

import uuid

import pytest
from fincore_common import EventEnvelope, EventType

from app.domain.fraud_check import FraudCheck, FraudDecision
from app.services.outbox import fraud_outbox_event
from tests.contracts import assert_valid_event


def _check(decision: FraudDecision, rules: list[str]) -> FraudCheck:
    return FraudCheck(
        id=uuid.uuid4(),
        operation_id=uuid.uuid4(),
        operation_type="PAYMENT",
        user_id=uuid.uuid4(),
        amount_minor=60_000_000,
        currency="UZS",
        score=55,
        decision=decision,
        rules_triggered=rules,
    )


@pytest.mark.parametrize(
    ("decision", "event_type"),
    [
        (FraudDecision.BLOCK, EventType.FRAUD_DETECTED),
        (FraudDecision.REVIEW, EventType.FRAUD_REVIEW_REQUIRED),
    ],
)
def test_block_and_review_events_match_their_contracts(
    decision: FraudDecision, event_type: EventType
) -> None:
    row = fraud_outbox_event(_check(decision, ["LARGE_AMOUNT", "HIGH_FREQUENCY"]))
    assert row is not None
    assert row.event_type == event_type.value

    envelope = EventEnvelope(
        event_type=EventType(row.event_type),
        producer="fraud-service",
        correlation_id=row.correlation_id,
        data=row.payload,
    )
    assert_valid_event(envelope.model_dump(mode="json"))


def test_allow_publishes_nothing() -> None:
    assert fraud_outbox_event(_check(FraudDecision.ALLOW, [])) is None
