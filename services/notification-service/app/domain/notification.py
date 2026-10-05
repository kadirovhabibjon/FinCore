import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Notification(Base):
    """A record of one dispatched notification, and what the customer
    sees behind the bell in the web app. Doubles as this consumer's
    idempotency guard (spec Section 14.3): `event_id` is the upstream
    `EventEnvelope.event_id`, and UNIQUE(event_id, recipient_user_id) is
    what actually stops a redelivered event (Section 14.1's
    at-least-once delivery, e.g. after a crash between processing and
    offset commit) from notifying the same person twice — the pre-check
    in app/services/consumer.py is only the fast path. One event can
    notify two people: a completed transfer tells the sender and the
    recipient.
    """

    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipient_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    notification_type: Mapped[str] = mapped_column(String(64), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # When the customer opened the bell with this in it; NULL = unread.
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "event_id", "recipient_user_id", name="uq_notifications_event_recipient"
        ),
    )
