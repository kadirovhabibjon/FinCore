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
from sqlalchemy.dialects.postgresql import ENUM, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.transfer import FraudDecision


class PaymentStatus(enum.StrEnum):
    """State machine (spec Section 11), enforced the same way Transfer's
    is: every transition is an atomic `UPDATE ... WHERE status =
    :expected` (`PaymentRepository.transition_status`), never assumed
    from in-memory state.

    CREATED             -> PROCESSING | FAILED | EXPIRED
    PROCESSING          -> SUCCESS | FAILED
    SUCCESS             -> REFUNDED (full) | PARTIALLY_REFUNDED
    PARTIALLY_REFUNDED  -> REFUNDED
    FAILED, EXPIRED, REFUNDED -> terminal
    """

    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    EXPIRED = "EXPIRED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    REFUNDED = "REFUNDED"


def _generate_reference() -> str:
    return f"PAY-{uuid.uuid4().hex[:12].upper()}"


class Payment(Base):
    """A business operation: a user paying a merchant (spec Section 11).
    Distinct from Transfer even though both eventually produce ledger
    postings — a payment additionally goes through a ledger hold
    (reserve -> capture) rather than posting directly, and can be
    partially or fully refunded afterward.
    """

    __tablename__ = "payments"

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
    merchant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("merchants.id"), nullable=False, index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, name="payment_status", native_enum=True),
        nullable=False,
        default=PaymentStatus.CREATED,
        server_default=PaymentStatus.CREATED.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # postgresql.ENUM specifically, not generic sqlalchemy.Enum: only the
    # dialect-specific class actually honors create_type=False when
    # reusing a native enum type another table already created —
    # confirmed empirically earlier in this project (see the matching
    # comment in ledger-service's app/domain/balance.py).
    fraud_decision: Mapped[FraudDecision | None] = mapped_column(
        ENUM(FraudDecision, name="fraud_decision", create_type=False),
        nullable=True,
    )
    # ledger-service's Hold id, once one exists (spec Section 8.4's
    # reserve -> capture) — nullable because a payment can fail before a
    # hold is ever created (e.g. fraud BLOCK), and used by both the
    # recovery worker (retrying a capture whose outcome was unknown) and
    # the refund flow, which needs to know a capture actually happened.
    hold_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Running total across every Refund row for this payment — the
    # column, not a live SUM() over refunds, is what
    # RefundRepository.transition_status\-style atomic updates guard
    # with a WHERE clause, so "total refunds <= captured amount" (spec
    # Section 11) is enforced by the database, not just application code.
    refunded_amount_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
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
        CheckConstraint("amount_minor > 0", name="ck_payments_amount_positive"),
        CheckConstraint(
            "refunded_amount_minor >= 0 AND refunded_amount_minor <= amount_minor",
            name="ck_payments_refunded_amount_within_bounds",
        ),
    )
