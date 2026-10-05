import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NewsItem(Base):
    """One article from a public news feed, as the feed itself describes
    it: headline, summary and a link to the publisher. Never the full
    article - that stays on the publisher's site."""

    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # The publisher's host, e.g. "cbu.uz"; shown as the source.
    source: Mapped[str] = mapped_column(String(100), nullable=False)
    # The feed's own identifier for the article; with `source`, what
    # makes fetching the same feed again a no-op.
    guid: Mapped[str] = mapped_column(String(500), nullable=False)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    url: Mapped[str] = mapped_column(String(1000), nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    __table_args__ = (UniqueConstraint("source", "guid", name="uq_news_items_source_guid"),)


class NewsRead(Base):
    """When a customer last opened the news. News is the same for
    everyone, so "unread" is not stored per article: it is whatever
    arrived after this moment."""

    __tablename__ = "news_reads"

    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
