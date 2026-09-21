import enum
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookDeliveryStatus(enum.StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    # Terminal: attempts exhausted max_delivery_attempts. Not retried
    # further automatically — same "give up, keep the record" reasoning
    # as notification-service's DeadLetter.
    FAILED = "FAILED"


class WebhookDelivery(Base):
    """One (endpoint, event) pair to deliver — the unit of retry state
    (spec Section 17). `UNIQUE(endpoint_id, event_id)` is this service's
    idempotency guard against Kafka's at-least-once redelivery (spec
    Section 14.1): re-processing the same event for the same endpoint is
    a no-op, not a second delivery row (app/services/consumer.py).

    `payload` is captured once, at creation time, from the inbound
    `EventEnvelope` — not re-derived from `event_type` at delivery time —
    so a delivery attempt always sends exactly what was true when the
    event was received, even if replayed much later.
    """

    __tablename__ = "webhook_deliveries"
    __table_args__ = (
        UniqueConstraint("endpoint_id", "event_id", name="uq_delivery_endpoint_event"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    endpoint_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("webhook_endpoints.id"), nullable=False, index=True
    )
    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[WebhookDeliveryStatus] = mapped_column(
        Enum(WebhookDeliveryStatus, name="webhook_delivery_status", native_enum=True),
        nullable=False,
        default=WebhookDeliveryStatus.PENDING,
        server_default=WebhookDeliveryStatus.PENDING.value,
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Drives the delivery worker's polling query (app/services/delivery.py)
    # — set to "now" at creation so a fresh delivery is picked up on the
    # very next pass, then pushed forward by backoff after each failure.
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_error: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
