import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DeadLetter(Base):
    """A message this consumer gave up on (spec Section 16: "dead-letter
    topics and manual replay") — either a permanent failure routed here
    immediately, or a transient one that exhausted its retry attempts.
    Kept queryable here, separately from the "transfers-dlt" Kafka topic
    it's also published to, specifically so there's something to list
    and manually replay (app/api/internal/dead_letters.py) without
    needing a Kafka consumer console.
    """

    __tablename__ = "dead_letters"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    topic: Mapped[str] = mapped_column(String(64), nullable=False)
    envelope: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    last_error: Mapped[str] = mapped_column(String(2000), nullable=False)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    replayed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
