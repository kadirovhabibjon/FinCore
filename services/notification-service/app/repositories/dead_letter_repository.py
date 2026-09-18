from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.dead_letter import DeadLetter


class DeadLetterRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, dead_letter_id: UUID) -> DeadLetter | None:
        return await self._session.get(DeadLetter, dead_letter_id)

    async def list_unreplayed(self, *, limit: int = 100) -> list[DeadLetter]:
        result = await self._session.execute(
            select(DeadLetter)
            .where(DeadLetter.replayed_at.is_(None))
            .order_by(DeadLetter.created_at)
            .limit(limit)
        )
        return list(result.scalars().all())
