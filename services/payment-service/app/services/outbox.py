import logging
from datetime import UTC, datetime

from fincore_common import EventEnvelope, EventType
from fincore_common.kafka import EventProducer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

# One topic per aggregate type (spec Section 14.1's OutboxEvent has its
# own aggregate_type column for exactly this) — Transfer and Payment
# events are unrelated to each other and shouldn't share ordering
# guarantees or a consumer group's own offset tracking.
_TOPIC_BY_AGGREGATE_TYPE = {
    "Transfer": lambda: settings.transfers_topic,
    "Payment": lambda: settings.payments_topic,
}


async def relay_outbox_events(session: AsyncSession, producer: EventProducer) -> int:
    """Publishes unpublished `outbox_events` rows to Kafka, oldest
    first, marking each published only after a successful send (spec
    Section 14.1). If the process crashes between publish and
    mark-published, the row is republished on the next pass — its
    `id` (reused as `EventEnvelope.event_id`) stays the same across
    attempts, which is what lets a consumer deduplicate rather than
    act on the same operation twice (Section 14.3).
    """
    repository = OutboxRepository(session)
    rows = await repository.list_unpublished(limit=settings.outbox_relay_batch_size)

    for row in rows:
        topic_for = _TOPIC_BY_AGGREGATE_TYPE.get(row.aggregate_type)
        if topic_for is None:
            logger.error("no topic configured for aggregate_type %s; skipping", row.aggregate_type)
            continue

        envelope = EventEnvelope(
            event_id=row.id,
            event_type=EventType(row.event_type),
            producer=settings.service_name,
            correlation_id=row.correlation_id,
            data=row.payload,
        )
        await producer.send(topic_for(), key=row.aggregate_id, envelope=envelope)
        await repository.mark_published(row.id, published_at=datetime.now(UTC))

    return len(rows)
