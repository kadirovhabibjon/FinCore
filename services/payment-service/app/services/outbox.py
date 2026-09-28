import logging
from datetime import UTC, datetime
from uuid import UUID

from fincore_common import EventEnvelope, EventType
from fincore_common.kafka import EventProducer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import OUTBOX_BACKLOG
from app.db import session as db_session
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
    """Publishes one batch of unpublished `outbox_events` rows to Kafka,
    oldest first, and marks them published only after every send in the
    batch is acknowledged (spec Section 14.1). Returns how many were
    published.

    The batch is sent as one unit (EventProducer.send_many) and marked in
    one UPDATE — a relay that awaited a send and a commit per row spent
    minutes on a single batch once request handling saturated the event
    loop (README, "Load testing"). If the process crashes or a send
    fails before the batch is marked, the whole batch is republished on
    the next pass; each row's `id` (reused as `EventEnvelope.event_id`)
    stays the same across attempts, which is what lets a consumer
    deduplicate rather than act on the same operation twice
    (Section 14.3).
    """
    repository = OutboxRepository(session)
    rows = await repository.list_unpublished(limit=settings.outbox_relay_batch_size)

    messages: list[tuple[str, str, EventEnvelope]] = []
    event_ids: list[UUID] = []
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
        messages.append((topic_for(), row.aggregate_id, envelope))
        event_ids.append(row.id)

    if not messages:
        return 0
    await producer.send_many(messages)
    await repository.mark_published(event_ids, published_at=datetime.now(UTC))
    return len(event_ids)


async def drain_outbox(producer: EventProducer) -> int:
    """Relays batch after batch until one comes back short, then
    returns — the relay loop (app/main.py) only sleeps once caught up.

    Sleeping after *every* batch capped throughput at batch_size /
    interval (100 rows / 5s = 20 events/s): under sustained load
    (tests/load) the backlog grew past 4,000 events and downstream
    consumers saw them minutes late. Stopping on a short *published*
    count, not a short fetch, means a row that can't be routed never
    turns this into a hot loop.
    """
    total = 0
    while True:
        async with db_session.async_session_factory() as session:
            published = await relay_outbox_events(session, producer)
            # Per batch, not per drain: a drain can run for minutes under
            # load, and a gauge updated only at the end sits stale for
            # exactly the stretch it exists to show.
            OUTBOX_BACKLOG.set(await OutboxRepository(session).count_unpublished())
        total += published
        if published < settings.outbox_relay_batch_size:
            return total

