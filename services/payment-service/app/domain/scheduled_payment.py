import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, Index, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base
from app.domain.template import TemplateKind


class ScheduleInterval(enum.StrEnum):
    # `day` is the ISO weekday, 1 (Monday) to 7 (Sunday).
    WEEKLY = "WEEKLY"
    # `day` is the day of the month, 1 to 28 - every month has those.
    MONTHLY = "MONTHLY"


class ScheduleStatus(enum.StrEnum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"


class ScheduledPayment(Base):
    """A payment FinCore makes for the customer on a schedule: the same
    service payment or transfer, the same amount, every week or month.

    Unlike a template this *is* an instruction - money moves without the
    customer pressing anything - so it carries everything a payment
    needs (the wallet and the amount are not optional) and each run goes
    through the ordinary saga, with every rule of a payment: balance,
    daily limit, card block, fraud check. See app/services/autopay.py
    for how a run is made exactly once or not at all.
    """

    __tablename__ = "scheduled_payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    owner_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    kind: Mapped[TemplateKind] = mapped_column(
        Enum(TemplateKind, name="template_kind", native_enum=True, create_type=False),
        nullable=False,
    )
    service_code: Mapped[str | None] = mapped_column(String(32), nullable=True)
    service_account: Mapped[str | None] = mapped_column(String(64), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(16), nullable=True)
    recipient_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_wallet_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    interval: Mapped[ScheduleInterval] = mapped_column(
        Enum(ScheduleInterval, name="schedule_interval", native_enum=True), nullable=False
    )
    day: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ScheduleStatus] = mapped_column(
        Enum(ScheduleStatus, name="schedule_status", native_enum=True),
        nullable=False,
        default=ScheduleStatus.ACTIVE,
        server_default=ScheduleStatus.ACTIVE.value,
    )
    # When it runs next. The worker claims a run by moving this on.
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    # The last run: when, and how it ended - the operation's status
    # (COMPLETED, SUCCESS, FAILED, PENDING...), or NOT_RUN with the
    # reason in `last_error` when no operation could even be started.
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_operation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        CheckConstraint(
            "(kind = 'SERVICE' AND service_code IS NOT NULL AND service_account IS NOT NULL"
            " AND card_number IS NULL) OR "
            "(kind = 'TRANSFER' AND card_number IS NOT NULL AND service_code IS NULL"
            " AND service_account IS NULL)",
            name="ck_scheduled_payments_fields_match_kind",
        ),
        CheckConstraint("amount_minor > 0", name="ck_scheduled_payments_amount_positive"),
        CheckConstraint(
            "(interval = 'WEEKLY' AND day BETWEEN 1 AND 7) OR "
            "(interval = 'MONTHLY' AND day BETWEEN 1 AND 28)",
            name="ck_scheduled_payments_day_fits_interval",
        ),
        # What the worker looks for: active schedules that are due.
        Index("ix_scheduled_payments_due", "status", "next_run_at"),
    )
