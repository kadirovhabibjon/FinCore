from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.hold import Hold


class HoldRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_source(self, source_service: str, source_id: str) -> Hold | None:
        result = await self._session.execute(
            select(Hold).where(
                Hold.source_service == source_service, Hold.source_id == source_id
            )
        )
        return result.scalar_one_or_none()

    async def get_locked(self, hold_id: UUID) -> Hold | None:
        """Locks the hold row itself (not just the account balance), so
        two concurrent capture/release calls for the *same* hold are
        serialized — the second one sees the first's already-applied
        status change instead of racing it.
        """
        return await self._session.get(Hold, hold_id, with_for_update=True)
