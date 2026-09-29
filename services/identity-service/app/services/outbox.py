import logging
from datetime import UTC, datetime
from uuid import UUID

from fincore_common import EventEnvelope, EventType, get_correlation_id
from fincore_common.kafka import EventProducer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.metrics import OUTBOX_BACKLOG
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.domain.user import User, UserStatus
from app.repositories.outbox_repository import OutboxRepository

logger = logging.getLogger(__name__)

# Which event a status change emits. user.blocked is spec Section 14.3's
# own name; the other two cover the rest of the admin status API so no
# status change goes unaudited.
STATUS_EVENTS = {
    UserStatus.BLOCKED: EventType.USER_BLOCKED,
    UserStatus.SUSPENDED: EventType.USER_SUSPENDED,
    UserStatus.ACTIVE: EventType.USER_REACTIVATED,
}


def user_outbox_event(
    user: User, event_type: EventType, *, actor_user_id: UUID | None, **facts: str | None
) -> OutboxEvent:
    """An account event, added by the caller to the same session — and so
    the same transaction — as the change it describes. Ids and status
    only: no email, phone or name ever goes on the wire (spec Section
    14.2: "never secrets or full sensitive profiles").
    """
    return OutboxEvent(
        aggregate_type="User",
        aggregate_id=str(user.id),
        event_type=event_type.value,
        correlation_id=get_correlation_id(),
        payload={
            "user_id": str(user.id),
            "actor_user_id": str(actor_user_id) if actor_user_id else None,
            "status": user.status.value,
            **facts,
        },
    )


async def relay_outbox_events(session: AsyncSession, producer: EventProducer) -> int:
    """Publishes one batch of unpublished rows, oldest first, and marks
    them published only after the whole batch is acknowledged — the same
    at-least-once relay as payment-service's (each row's id is reused as
    the event_id, so a republished batch is deduplicated downstream).
    """
    repository = OutboxRepository(session)
    rows = await repository.list_unpublished(limit=settings.outbox_relay_batch_size)
    if not rows:
        return 0

    messages = [
        (
            settings.users_topic,
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
    """Relays batch after batch until one comes back short (see
    payment-service's drain_outbox for why it doesn't sleep per batch)."""
    total = 0
    while True:
        async with db_session.async_session_factory() as session:
            published = await relay_outbox_events(session, producer)
            OUTBOX_BACKLOG.set(await OutboxRepository(session).count_unpublished())
        total += published
        if published < settings.outbox_relay_batch_size:
            return total
