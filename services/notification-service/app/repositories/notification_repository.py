from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists_for_event(self, event_id: UUID) -> bool:
        result = await self._session.execute(
            select(Notification.id).where(Notification.event_id == event_id)
        )
        return result.scalar_one_or_none() is not None
