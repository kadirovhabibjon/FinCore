import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class WebhookEndpointStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    # spec Section 17: "failure handling (endpoint auto-disabled after
    # repeated failures)" — set by the delivery worker, cleared only by
    # an explicit re-enable call (app/services/endpoints.py), never
    # automatically, since the merchant's endpoint needs to actually be
    # fixed first.
    DISABLED = "DISABLED"


class WebhookEndpoint(Base):
    """A merchant-registered callback target (spec Section 17).
    `owner_user_id` is captured once, at registration time, from
    payment-service's internal merchant-ownership check
    (app/services/merchants.py) rather than re-verified on every read —
    merchant ownership doesn't change in this system, the same
    assumption payment-service itself makes about its own `merchants`
    rows.
    """

    __tablename__ = "webhook_endpoints"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    merchant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    url: Mapped[str] = mapped_column(String(2048), nullable=False)
    # HMAC-SHA256 signing key (spec Section 17: "per-endpoint secrets,
    # stored securely, rotatable"). Returned to the caller only at
    # creation and rotation time, never on a plain GET — see
    # WebhookEndpointResponse vs WebhookEndpointWithSecretResponse.
    secret: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[WebhookEndpointStatus] = mapped_column(
        Enum(WebhookEndpointStatus, name="webhook_endpoint_status", native_enum=True),
        nullable=False,
        default=WebhookEndpointStatus.ACTIVE,
        server_default=WebhookEndpointStatus.ACTIVE.value,
    )
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
