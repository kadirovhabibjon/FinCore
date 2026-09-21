import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RefundStatus(enum.StrEnum):
    """A minimal state machine — not the full Payment/Transfer saga
    treatment, but the same underlying reason those have one: the
    ledger posting a refund makes is itself only reachable over the
    network, so an unknown outcome (timeout, 5xx) has to leave *some*
    durable, retriable state rather than nothing at all — otherwise a
    retried refund request would mint a fresh id each time and risk a
    duplicate posting instead of safely retrying the same one.
    """

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class Refund(Base):
    """One refund against a captured Payment (spec Section 11: "refunds
    as new postings, never by editing old ones"). A completed Refund
    row is append-only from that point on; `Payment.refunded_amount_minor`
    is what accumulates across possibly several refunds for one payment.
    """

    __tablename__ = "refunds"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    payment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id"), nullable=False, index=True
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[RefundStatus] = mapped_column(
        Enum(RefundStatus, name="refund_status", native_enum=True),
        nullable=False,
        default=RefundStatus.PENDING,
        server_default=RefundStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
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

    __table_args__ = (CheckConstraint("amount_minor > 0", name="ck_refunds_amount_positive"),)
