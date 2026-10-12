import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class SavingsGoal(Base):
    """Money a customer sets aside for something: a name, a target, and
    how much is in it.

    The money is real: it leaves the wallet for the currency's pooled
    SAVINGS account in the ledger (ADR-0010) and comes back the same
    way. Which goal holds how much of that pool is recorded here, as
    `saved_minor`, changed only together with the movement that changed
    it - so the goals of a currency always add up to its pool, less
    whatever is on its way back out.
    """

    __tablename__ = "savings_goals"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    target_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    # In the goal and not already on its way out: a withdrawal takes its
    # amount off here when it starts, and puts it back if it fails.
    saved_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0, server_default="0"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Set when the owner closed it (only possible once it is empty). Its
    # movements stay: they are records of money that moved.
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("target_minor > 0", name="ck_savings_goals_target_positive"),
        # The database's own word on it: a goal never holds less than nothing.
        CheckConstraint("saved_minor >= 0", name="ck_savings_goals_saved_not_negative"),
    )


class MovementDirection(enum.StrEnum):
    # Wallet -> goal.
    DEPOSIT = "DEPOSIT"
    # Goal -> wallet.
    WITHDRAW = "WITHDRAW"


class MovementStatus(enum.StrEnum):
    """PENDING -> COMPLETED | FAILED, each by an atomic
    `UPDATE ... WHERE status = 'PENDING'`. PENDING also covers "the
    ledger did not answer": the recovery worker asks again."""

    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


def _generate_reference() -> str:
    return f"SAV-{uuid.uuid4().hex[:12].upper()}"


class SavingsMovement(Base):
    """One movement of money into or out of a goal: a single posting
    between the customer's wallet and the SAVINGS pool."""

    __tablename__ = "savings_movements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference: Mapped[str] = mapped_column(
        String(32), unique=True, nullable=False, default=_generate_reference
    )
    goal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("savings_goals.id"), nullable=False
    )
    owner_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The currency's SAVINGS account, looked up when the movement was made.
    pool_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    direction: Mapped[MovementDirection] = mapped_column(
        Enum(MovementDirection, name="savings_direction", native_enum=True), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    status: Mapped[MovementStatus] = mapped_column(
        Enum(MovementStatus, name="savings_status", native_enum=True),
        nullable=False,
        default=MovementStatus.PENDING,
        server_default=MovementStatus.PENDING.value,
    )
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    idempotency_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("idempotency_keys.id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="ck_savings_movements_amount_positive"),
        Index("ix_savings_movements_goal", "goal_id", "created_at"),
        # What the recovery worker looks for.
        Index("ix_savings_movements_status", "status", "updated_at"),
    )
