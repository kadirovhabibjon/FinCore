from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, status
from fincore_common import normalize_card_number
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.core.amounts import parse_positive_amount
from app.core.exceptions import (
    AmountOutOfRangeError,
    CurrencyMismatchError,
    InvalidScheduleError,
    InvalidTemplateError,
    ScheduledPaymentNotFoundError,
    ServiceNotFoundError,
    TooManyScheduledPaymentsError,
    WalletNotFoundError,
)
from app.db.session import get_db
from app.domain.scheduled_payment import ScheduledPayment, ScheduleInterval, ScheduleStatus
from app.domain.template import TemplateKind
from app.services import autopay, billers, ledger
from app.services.recipients import find_recipient

router = APIRouter(prefix="/api/v1/scheduled-payments", tags=["scheduled-payments"])

# A handful of standing instructions is a household's worth; more than
# this is likelier a mistake or a script than a need.
MAX_SCHEDULED = 20


class CreateScheduledPaymentRequest(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    kind: TemplateKind
    # SERVICE: the provider's code and the account there, as typed.
    service_code: str | None = Field(default=None, max_length=32)
    account: str | None = Field(default=None, max_length=64)
    # TRANSFER: the recipient's FinCore card number.
    card_number: str | None = Field(default=None, max_length=32)
    source_wallet_id: UUID
    # Decimal string, in the wallet's currency. Paid every time.
    amount: str = Field(min_length=1, max_length=32)
    interval: ScheduleInterval
    # WEEKLY: 1 (Monday) to 7 (Sunday). MONTHLY: 1 to 28.
    day: int

    @field_validator("name")
    @classmethod
    def _one_line(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("must not be blank")
        return cleaned


class UpdateScheduledPaymentRequest(BaseModel):
    status: ScheduleStatus


class ScheduledPaymentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    kind: TemplateKind
    service_code: str | None
    service_account: str | None
    card_number: str | None
    recipient_name: str | None
    source_wallet_id: UUID
    currency: str
    amount_minor: int
    interval: ScheduleInterval
    day: int
    status: ScheduleStatus
    # When it runs next (while ACTIVE).
    next_run_at: datetime
    # The last run: when, how it ended - an operation's status, RUNNING
    # while one is being made, or NOT_RUN with the reason in
    # `last_error` - and the operation it made, if any.
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    last_operation_id: UUID | None
    created_at: datetime


async def _owned(session: AsyncSession, scheduled_id: UUID, user_id: UUID) -> ScheduledPayment:
    scheduled = await session.get(ScheduledPayment, scheduled_id)
    if scheduled is None or scheduled.owner_user_id != user_id:
        raise ScheduledPaymentNotFoundError(str(scheduled_id))
    return scheduled


@router.get("", response_model=list[ScheduledPaymentResponse])
async def list_my_scheduled_payments(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[ScheduledPaymentResponse]:
    """The caller's scheduled payments, soonest first."""
    result = await session.execute(
        select(ScheduledPayment)
        .where(ScheduledPayment.owner_user_id == user.user_id)
        .order_by(ScheduledPayment.next_run_at, ScheduledPayment.id)
    )
    return [ScheduledPaymentResponse.model_validate(item) for item in result.scalars().all()]


@router.post("", response_model=ScheduledPaymentResponse, status_code=status.HTTP_201_CREATED)
async def schedule_payment(
    payload: CreateScheduledPaymentRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> ScheduledPaymentResponse:
    """A payment FinCore will make for the caller every week or month,
    at 04:00 UTC, from one of their wallets: a service provider and
    account, or a recipient's card. Checked now the way the payment
    itself would be; each run is then an ordinary operation, with every
    rule of one. Nothing is paid by creating it."""
    limit = 7 if payload.interval is ScheduleInterval.WEEKLY else 28
    if not 1 <= payload.day <= limit:
        raise InvalidScheduleError(f"day must be from 1 to {limit} for {payload.interval.value}")

    wallet = await ledger.ledger_client.get_wallet(
        payload.source_wallet_id, user_bearer_token=user.access_token
    )
    if wallet is None:
        raise WalletNotFoundError(str(payload.source_wallet_id))
    amount_minor = parse_positive_amount(payload.amount, wallet.currency)

    scheduled = ScheduledPayment(
        owner_user_id=user.user_id,
        name=payload.name,
        kind=payload.kind,
        source_wallet_id=wallet.id,
        currency=wallet.currency,
        amount_minor=amount_minor,
        interval=payload.interval,
        day=payload.day,
        next_run_at=autopay.next_run(payload.interval, payload.day, after=datetime.now(UTC)),
    )
    if payload.kind is TemplateKind.SERVICE:
        if not payload.service_code or not payload.account or payload.card_number:
            raise InvalidTemplateError("a service payment has service_code and account")
        biller = billers.find(payload.service_code)
        if biller is None:
            raise ServiceNotFoundError(payload.service_code)
        if biller.currency != wallet.currency:
            raise CurrencyMismatchError(
                f"{biller.name} is paid in {biller.currency}; this wallet is {wallet.currency}"
            )
        if not biller.min_amount_minor <= amount_minor <= biller.max_amount_minor:
            raise AmountOutOfRangeError(f"{biller.name} does not take this amount")
        scheduled.service_code = biller.code
        scheduled.service_account = billers.clean_account(biller, payload.account)
    else:
        if not payload.card_number or payload.service_code or payload.account:
            raise InvalidTemplateError("a transfer has card_number")
        recipient = await find_recipient(payload.card_number, caller_user_id=user.user_id)
        if recipient.currency != wallet.currency:
            raise CurrencyMismatchError(
                f"that card is {recipient.currency}; this wallet is {wallet.currency}"
            )
        scheduled.card_number = normalize_card_number(payload.card_number)
        scheduled.recipient_name = recipient.display_name

    count = await session.execute(
        select(func.count())
        .select_from(ScheduledPayment)
        .where(ScheduledPayment.owner_user_id == user.user_id)
    )
    if count.scalar_one() >= MAX_SCHEDULED:
        raise TooManyScheduledPaymentsError(f"at most {MAX_SCHEDULED}; delete one first")

    session.add(scheduled)
    await session.commit()
    await session.refresh(scheduled)
    return ScheduledPaymentResponse.model_validate(scheduled)


@router.patch("/{scheduled_id}", response_model=ScheduledPaymentResponse)
async def pause_or_resume(
    scheduled_id: UUID,
    payload: UpdateScheduledPaymentRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> ScheduledPaymentResponse:
    """Pauses a scheduled payment, or resumes it. Resuming schedules the
    next occurrence from now: runs missed while paused are not made up."""
    scheduled = await _owned(session, scheduled_id, user.user_id)
    if payload.status is ScheduleStatus.ACTIVE and scheduled.status is not ScheduleStatus.ACTIVE:
        scheduled.next_run_at = autopay.next_run(
            scheduled.interval, scheduled.day, after=datetime.now(UTC)
        )
    scheduled.status = payload.status
    await session.commit()
    await session.refresh(scheduled)
    return ScheduledPaymentResponse.model_validate(scheduled)


@router.delete("/{scheduled_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scheduled_payment(
    scheduled_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Stops it for good. Operations it already made stay in the history."""
    scheduled = await _owned(session, scheduled_id, user.user_id)
    await session.delete(scheduled)
    await session.commit()
