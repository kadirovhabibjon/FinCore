from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.news import NewsItem, NewsRead

# Someone who has never opened the news isn't shown the whole backlog as
# unread: only what arrived in the last day.
_FIRST_VISIT_WINDOW = timedelta(days=1)


class NewsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_recent(self, *, limit: int, offset: int) -> list[NewsItem]:
        result = await self._session.execute(
            select(NewsItem)
            .order_by(NewsItem.published_at.desc(), NewsItem.id)
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def get(self, news_id: UUID) -> NewsItem | None:
        return await self._session.get(NewsItem, news_id)

    async def seen_at(self, user_id: UUID) -> datetime:
        """The moment after which news counts as unread for this user."""
        read = await self._session.get(NewsRead, user_id)
        return read.seen_at if read else datetime.now(UTC) - _FIRST_VISIT_WINDOW

    async def count_since(self, moment: datetime) -> int:
        result = await self._session.execute(
            select(func.count()).select_from(NewsItem).where(NewsItem.fetched_at > moment)
        )
        return int(result.scalar_one())

    async def mark_seen(self, user_id: UUID) -> None:
        now = func.now()
        await self._session.execute(
            insert(NewsRead)
            .values(user_id=user_id, seen_at=now)
            .on_conflict_do_update(index_elements=[NewsRead.user_id], set_={"seen_at": now})
        )
