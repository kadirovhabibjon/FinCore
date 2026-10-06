from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.announcement import Announcement, AnnouncementRead

# Someone opening the bell for the first time is not shown every
# announcement ever made as unread: only the last week's.
_FIRST_VISIT_WINDOW = timedelta(days=7)


class AnnouncementRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    def add(self, announcement: Announcement) -> None:
        self._session.add(announcement)

    async def get(self, announcement_id: UUID) -> Announcement | None:
        announcement = await self._session.get(Announcement, announcement_id)
        if announcement is None or announcement.deleted_at is not None:
            return None
        return announcement

    async def list_recent(self, *, limit: int) -> list[Announcement]:
        result = await self._session.execute(
            select(Announcement)
            .where(Announcement.deleted_at.is_(None))
            .order_by(Announcement.created_at.desc(), Announcement.id)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def seen_at(self, user_id: UUID) -> datetime:
        """The moment after which an announcement is unread for this user."""
        read = await self._session.get(AnnouncementRead, user_id)
        return read.seen_at if read else datetime.now(UTC) - _FIRST_VISIT_WINDOW

    async def count_since(self, moment: datetime) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(Announcement)
            .where(Announcement.deleted_at.is_(None), Announcement.created_at > moment)
        )
        return int(result.scalar_one())

    async def mark_seen(self, user_id: UUID) -> None:
        now = func.now()
        await self._session.execute(
            insert(AnnouncementRead)
            .values(user_id=user_id, seen_at=now)
            .on_conflict_do_update(
                index_elements=[AnnouncementRead.user_id], set_={"seen_at": now}
            )
        )
