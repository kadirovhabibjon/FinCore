import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class OutboxEvent(Base):
    """The transactional outbox (spec Section 14.1): written in the same
    local DB transaction as the business change it describes, so a
    committed change can never silently fail to get an event — the
    relay (app/services/outbox.py) is a separate step that publishes
    unpublished rows to Kafka afterward, not part of this transaction.
    """

    __tablename__ = "outbox_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aggregate_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Also used as the Kafka partition key (app/services/outbox.py) —
    # every event for one aggregate lands on the same partition, so a
    # consumer sees them in order.
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # This row's own id doubles as the eventual EventEnvelope.event_id
    # (spec Section 14.1's "OutboxEvent - id (event_id, UUID)") — fixed
    # at write time so a row the relay republishes after a crash (before
    # marking it published) carries the *same* event_id both times,
    # which is what lets a consumer deduplicate (Section 14.3).
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    # Captured now, not at publish time: the outbox relay is a
    # background loop with no request of its own to inherit a
    # correlation id from.
    correlation_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
