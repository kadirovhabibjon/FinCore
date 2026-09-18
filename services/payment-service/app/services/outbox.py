import logging
from datetime import UTC, datetime

from fincore_common import EventEnvelope, EventType
from fincore_common.kafka import EventProducer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)


async def relay_outbox_events(session: AsyncSession, producer: EventProducer) -> int:
    """Publishes unpublished `outbox_events` rows to Kafka, oldest
    first, marking each published only after a successful send (spec
    Section 14.1). If the process crashes between publish and
    mark-published, the row is republished on the next pass — its
    `id` (reused as `EventEnvelope.event_id`) stays the same across
    attempts, which is what lets a consumer deduplicate rather than
    act on the same transfer twice (Section 14.3).

    All Transfer events go to one topic today (`settings.transfers_topic`)
    since Transfer is the only aggregate type payment-service's outbox
    carries; a second aggregate type would need this to pick a topic per
    `row.aggregate_type` instead of hardcoding one.
    """
    repository = OutboxRepository(session)
    rows = await repository.list_unpublished(limit=settings.outbox_relay_batch_size)

    for row in rows:
        envelope = EventEnvelope(
            event_id=row.id,
            event_type=EventType(row.event_type),
            producer=settings.service_name,
            correlation_id=row.correlation_id,
            data=row.payload,
        )
        await producer.send(settings.transfers_topic, key=row.aggregate_id, envelope=envelope)
        await repository.mark_published(row.id, published_at=datetime.now(UTC))

    return len(rows)
