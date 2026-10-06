import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MoneyRequestStatus(enum.StrEnum):
    """What is stored. What a customer sees also depends on the transfer
    a PAYING request points to (app/services/money_requests.py): that
    transfer completing makes the request PAID, its failing makes it
    PENDING again.
    """

    PENDING = "PENDING"
    # Claimed by a payment in progress: the atomic step that stops the
    # same request being paid twice.
    PAYING = "PAYING"
    PAID = "PAID"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"


def _generate_reference() -> str:
    return f"REQ-{uuid.uuid4().hex[:12].upper()}"


class MoneyRequest(Base):
    """One customer asking another for money. It moves nothing by
    itself: paying it creates an ordinary Transfer (and so goes through
    the same fraud check, ledger posting and idempotency as any other),
    recorded here as `transfer_id`.
    """

    __tablename__ = "money_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=_generate_reference
    )
    requester_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    # Where the money goes when the request is paid.
    requester_wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    payer_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    # Display names ("First L.") as they were when the request was made.
    requester_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    payer_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[MoneyRequestStatus] = mapped_column(
        Enum(MoneyRequestStatus, name="money_request_status", native_enum=True),
        nullable=False,
        default=MoneyRequestStatus.PENDING,
        server_default=MoneyRequestStatus.PENDING.value,
    )
    # The transfer paying it (the latest attempt, if an earlier one failed).
    transfer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_money_requests_amount_positive"),
        CheckConstraint(
            "requester_user_id != payer_user_id", name="ck_money_requests_not_from_self"
        ),
    )
