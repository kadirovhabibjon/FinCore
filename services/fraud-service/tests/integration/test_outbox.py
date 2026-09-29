import uuid

import pytest
from fincore_common.events import EventEnvelope
from fincore_common.kafka import EventConsumer, EventProducer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import session as db_session
from app.domain.fraud_check import FraudDecision
from app.domain.outbox import OutboxEvent
from app.services.outbox import relay_outbox_events
from app.services.risk_check import perform_risk_check
from app.services.rules import RiskContext, ScoringResult

pytestmark = pytest.mark.usefixtures("migrated_database")

_SCORES = {FraudDecision.ALLOW: 0, FraudDecision.REVIEW: 55, FraudDecision.BLOCK: 85}


class _FixedEngine:
    """Decides whatever the test says — the rules themselves are covered
    by test_rules.py; here only what gets written alongside matters."""

    def __init__(self, decision: FraudDecision) -> None:
        self._decision = decision

    async def score(self, session: AsyncSession, context: RiskContext) -> ScoringResult:
        rules = [] if self._decision == FraudDecision.ALLOW else ["LARGE_AMOUNT", "HIGH_FREQUENCY"]
        return ScoringResult(
            score=_SCORES[self._decision], decision=self._decision, rules_triggered=rules
        )


async def _check(decision: FraudDecision, operation_id: uuid.UUID | None = None) -> uuid.UUID:
    operation_id = operation_id or uuid.uuid4()
    async with db_session.async_session_factory() as session:
        await perform_risk_check(
            session,
            _FixedEngine(decision),  # type: ignore[arg-type]
            operation_id=operation_id,
            operation_type="TRANSFER",
            user_id=uuid.uuid4(),
            amount_minor=60_000_000,
            currency="UZS",
        )
    return operation_id


async def _events() -> list[OutboxEvent]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(OutboxEvent).order_by(OutboxEvent.created_at))
        return list(result.scalars().all())


async def test_block_and_review_are_recorded_and_allow_is_not() -> None:
    allowed = await _check(FraudDecision.ALLOW)
    reviewed = await _check(FraudDecision.REVIEW)
    blocked = await _check(FraudDecision.BLOCK)

    events = await _events()

    assert [(e.aggregate_id, e.event_type) for e in events] == [
        (str(reviewed), "fraud.review_required"),
        (str(blocked), "fraud.detected"),
    ]
    assert str(allowed) not in {e.aggregate_id for e in events}
    assert events[0].payload["decision"] == "REVIEW"
    assert events[0].payload["score"] == 55
    assert events[0].payload["rules_triggered"] == ["LARGE_AMOUNT", "HIGH_FREQUENCY"]


async def test_a_retried_check_does_not_record_a_second_event() -> None:
    operation_id = await _check(FraudDecision.REVIEW)
    await _check(FraudDecision.REVIEW, operation_id)  # idempotent replay

    assert [e.aggregate_id for e in await _events()] == [str(operation_id)]


async def test_the_relay_publishes_to_the_fraud_topic(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "fraud_topic", "test-fraud-events")
    operation_id = await _check(FraudDecision.BLOCK)

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            assert await relay_outbox_events(session, producer) == 1
        async with db_session.async_session_factory() as session:
            assert await relay_outbox_events(session, producer) == 0
    finally:
        await producer.stop()

    received: list[EventEnvelope] = []

    async def collect(event: EventEnvelope) -> None:
        received.append(event)

    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["test-fraud-events"],
        group_id="test-fraud-relay",
    )
    await consumer.start()
    try:
        await consumer.run(collect, max_messages=1)
    finally:
        await consumer.stop()

    [row] = await _events()
    assert row.published_at is not None
    assert received[0].event_id == row.id
    assert received[0].producer == "fraud-service"
    assert received[0].data["operation_id"] == str(operation_id)
