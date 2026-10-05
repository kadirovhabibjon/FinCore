from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.notification import Notification


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def exists_for_event(self, event_id: UUID, recipient_user_id: UUID) -> bool:
        result = await self._session.execute(
            select(Notification.id).where(
                Notification.event_id == event_id,
                Notification.recipient_user_id == recipient_user_id,
            )
        )
        return result.scalar_one_or_none() is not None

    async def list_for_user(self, user_id: UUID, *, limit: int, offset: int) -> list[Notification]:
        result = await self._session.execute(
            select(Notification)
            .where(Notification.recipient_user_id == user_id)
            .order_by(Notification.created_at.desc(), Notification.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_unread(self, user_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_user_id == user_id, Notification.read_at.is_(None))
        )
        return int(result.scalar_one())

    async def mark_all_read(self, user_id: UUID) -> None:
        await self._session.execute(
            update(Notification)
            .where(Notification.recipient_user_id == user_id, Notification.read_at.is_(None))
            .values(read_at=func.now())
        )
