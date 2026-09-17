import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    String,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TransferStatus(enum.StrEnum):
    """State machine (spec Section 7.3). Allowed transitions:

    PENDING     -> PROCESSING | CANCELLED | FAILED
    PROCESSING  -> COMPLETED  | FAILED
    COMPLETED   -> (terminal)
    FAILED      -> (terminal)
    CANCELLED   -> (terminal)

    Enforced in app/services/transfers.py, and guarded at the database
    update with `WHERE status = :expected` — never assumed from
    in-memory state alone.
    """

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FraudDecision(enum.StrEnum):
    ALLOW = "ALLOW"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


def _generate_reference() -> str:
    return f"TRF-{uuid.uuid4().hex[:12].upper()}"


class Transfer(Base):
    """A business operation: the user's *intention* to move money between
    two wallets (spec Section 7). Distinct from a ledger posting, which
    is the resulting accounting fact — one Transfer produces at most one
    posting, identified to ledger-service by this row's own id as
    `source_id` (Section 8.3's posting idempotency).
    """

    __tablename__ = "transfers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    reference: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=_generate_reference
    )
    initiator_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    source_wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    destination_wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[TransferStatus] = mapped_column(
        Enum(TransferStatus, name="transfer_status", native_enum=True),
        nullable=False,
        default=TransferStatus.PENDING,
        server_default=TransferStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    fraud_decision: Mapped[FraudDecision | None] = mapped_column(
        Enum(FraudDecision, name="fraud_decision", native_enum=True), nullable=True
    )
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("idempotency_keys.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_transfers_amount_positive"),
        CheckConstraint(
            "source_wallet_id != destination_wallet_id",
            name="ck_transfers_source_ne_destination",
        ),
    )
