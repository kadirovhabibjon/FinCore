from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.notifications import get_current_user_id
from app.core.exceptions import NewsNotFoundError
from app.db.session import get_db
from app.domain.news import NewsItem
from app.repositories.news_repository import NewsRepository

router = APIRouter(prefix="/api/v1/news", tags=["news"])


class NewsResponse(BaseModel):
    id: UUID
    title: str
    # The feed's own summary as plain text; may be empty.
    summary: str
    # The publisher's host, e.g. "cbu.uz".
    source: str
    # The full article, on the publisher's site.
    url: str
    published_at: datetime
    unread: bool

    @classmethod
    def of(cls, item: NewsItem, *, seen_at: datetime) -> "NewsResponse":
        return cls(
            id=item.id,
            title=item.title,
            summary=item.summary,
            source=item.source,
            url=item.url,
            published_at=item.published_at,
            unread=item.fetched_at > seen_at,
        )


class NewsListResponse(BaseModel):
    unread_count: int
    items: list[NewsResponse]


@router.get("", response_model=NewsListResponse)
async def list_news(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> NewsListResponse:
    """Banking and finance news from public feeds, newest first, and how
    many arrived since the caller last opened the news."""
    repository = NewsRepository(session)
    seen_at = await repository.seen_at(user_id)
    items = await repository.list_recent(limit=limit, offset=offset)
    return NewsListResponse(
        unread_count=await repository.count_since(seen_at),
        items=[NewsResponse.of(item, seen_at=seen_at) for item in items],
    )


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_news_read(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Everything fetched so far counts as seen by the caller. Idempotent."""
    await NewsRepository(session).mark_seen(user_id)
    await session.commit()


# Declared after /read, which a UUID path parameter would not match anyway.
@router.get("/{news_id}", response_model=NewsResponse)
async def get_news_item(
    news_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> NewsResponse:
    repository = NewsRepository(session)
    item = await repository.get(news_id)
    if item is None:
        raise NewsNotFoundError(str(news_id))
    return NewsResponse.of(item, seen_at=await repository.seen_at(user_id))
