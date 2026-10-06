import enum
import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Numeric,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ExchangeStatus(enum.StrEnum):
    """Where the two-step saga is (app/services/exchanges.py). The
    source currency is taken first and the destination currency given
    second, so at no point does a customer hold both.
    """

    # Created; the sale of the source currency is not confirmed.
    PENDING = "PENDING"
    # The source currency has left the customer's wallet; the
    # destination currency has not arrived yet.
    DEBITED = "DEBITED"
    COMPLETED = "COMPLETED"
    # The destination could not be credited; the source currency is on
    # its way back.
    REVERSING = "REVERSING"
    # Nothing moved, or what moved was returned.
    FAILED = "FAILED"


def _generate_reference() -> str:
    return f"EXC-{uuid.uuid4().hex[:12].upper()}"


class Exchange(Base):
    """A customer converting money between two of their own wallets in
    different currencies, at a rate fixed when it was created."""

    __tablename__ = "exchanges"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=_generate_reference
    )
    initiator_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    source_wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    destination_wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # FinCore's EXCHANGE accounts in each currency (ledger-service), looked
    # up once at creation so no later step of the saga depends on a lookup.
    source_position_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    destination_position_account_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    source_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    source_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    destination_amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    destination_currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Units of the destination currency per one unit of the source.
    rate: Mapped[Decimal] = mapped_column(Numeric(30, 15), nullable=False)
    status: Mapped[ExchangeStatus] = mapped_column(
        Enum(ExchangeStatus, name="exchange_status", native_enum=True),
        nullable=False,
        default=ExchangeStatus.PENDING,
        server_default=ExchangeStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("idempotency_keys.id"), nullable=False, unique=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("source_amount_minor > 0", name="ck_exchanges_source_positive"),
        CheckConstraint("destination_amount_minor > 0", name="ck_exchanges_destination_positive"),
        CheckConstraint(
            "source_currency != destination_currency", name="ck_exchanges_currencies_differ"
        ),
    )
