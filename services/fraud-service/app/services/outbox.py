import logging
from datetime import UTC, datetime

from fincore_common import EventEnvelope, EventType, get_correlation_id
from fincore_common.kafka import EventProducer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import OUTBOX_BACKLOG
from app.db import session as db_session
from app.domain.fraud_check import FraudCheck, FraudDecision
from app.domain.outbox import OutboxEvent
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

# spec Section 14.3's two fraud events. ALLOW, by far the most common
# decision, publishes nothing: it is still stored in fraud_checks and
# counted in fincore_fraud_checks_total, and auditing every allowed
# operation would add nothing the transfer/payment events don't already.
DECISION_EVENTS = {
    FraudDecision.BLOCK: EventType.FRAUD_DETECTED,
    FraudDecision.REVIEW: EventType.FRAUD_REVIEW_REQUIRED,
}


def fraud_outbox_event(check: FraudCheck) -> OutboxEvent | None:
    """The event for a decision, or None for ALLOW. Keyed by the
    operation (a transfer or payment id), so the audit trail files the
    decision next to that operation's own events.
    """
    event_type = DECISION_EVENTS.get(check.decision)
    if event_type is None:
        return None
    return OutboxEvent(
        aggregate_type="FraudCheck",
        aggregate_id=str(check.operation_id),
        event_type=event_type.value,
        correlation_id=get_correlation_id(),
        payload={
            "check_id": str(check.id),
            "operation_id": str(check.operation_id),
            "operation_type": check.operation_type,
            "initiator_user_id": str(check.user_id),
            "amount_minor": check.amount_minor,
            "currency": check.currency,
            "score": check.score,
            "decision": check.decision.value,
            "rules_triggered": list(check.rules_triggered),
        },
    )


async def relay_outbox_events(session: AsyncSession, producer: EventProducer) -> int:
    """One batch, oldest first, marked published only once the whole
    batch is acknowledged — the same at-least-once relay as
    payment-service's (each row's id is reused as the event_id)."""
    repository = OutboxRepository(session)
    rows = await repository.list_unpublished(limit=settings.outbox_relay_batch_size)
    if not rows:
        return 0

    messages = [
        (
            settings.fraud_topic,
            row.aggregate_id,
            EventEnvelope(
                event_id=row.id,
                event_type=EventType(row.event_type),
                producer=settings.service_name,
                correlation_id=row.correlation_id,
                data=row.payload,
            ),
        )
        for row in rows
    ]
    await producer.send_many(messages)
    await repository.mark_published([row.id for row in rows], published_at=datetime.now(UTC))
    return len(rows)


async def drain_outbox(producer: EventProducer) -> int:
    """Relays batch after batch until one comes back short."""
    total = 0
    while True:
        async with db_session.async_session_factory() as session:
            published = await relay_outbox_events(session, producer)
            OUTBOX_BACKLOG.set(await OutboxRepository(session).count_unpublished())
        total += published
        if published < settings.outbox_relay_batch_size:
            return total
