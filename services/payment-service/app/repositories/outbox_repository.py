from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.outbox import OutboxEvent


class OutboxRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_unpublished(self) -> int:
        """The true outbox backlog (spec Section 24's "outbox backlog
        (unpublished events)" metric) — `list_unpublished`'s own
        `limit` means its result length understates the backlog
        whenever it exceeds one relay pass's batch size.
        """
        result = await self._session.execute(
            select(func.count()).select_from(OutboxEvent).where(OutboxEvent.published_at.is_(None))
        )
        return result.scalar_one()

    async def list_unpublished(self, *, limit: int) -> list[OutboxEvent]:
        """Oldest first — preserves the order events were written in,
        for whatever ordering guarantee that's worth once they also
        share a Kafka partition key (app/services/outbox.py).
        """
        result = await self._session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_published(self, event_id: UUID, *, published_at: datetime) -> None:
        await self._session.execute(
            update(OutboxEvent)
            .where(OutboxEvent.id == event_id)
            .values(published_at=published_at)
        )
        await self._session.commit()
