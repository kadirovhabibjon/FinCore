import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MerchantStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Merchant(Base):
    """A business identity a user registers to receive payments (spec
    Section 21's `payment_db.merchants`). Deliberately minimal — the
    spec doesn't define a merchant onboarding flow beyond the table's
    existence, and payments settle into one pooled `MERCHANT_SETTLEMENT`
    ledger account per currency regardless of which merchant they're
    for (ADR-0002); this row exists so a payment has something concrete
    to reference and so its owner can list/manage it, not because the
    ledger needs it to route money.
    """

    __tablename__ = "merchants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[MerchantStatus] = mapped_column(
        Enum(MerchantStatus, name="merchant_status", native_enum=True),
        nullable=False,
        default=MerchantStatus.ACTIVE,
        server_default=MerchantStatus.ACTIVE.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
