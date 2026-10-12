"""Scheduled payments: the same service payment or transfer, made for
the customer every week or month.

**At most once.** A run is claimed before it is made: one statement
moves `next_run_at` on to the next occurrence, and only if it still
says what the worker read (`UPDATE ... WHERE next_run_at = :due`). Two
workers, or a worker and its own retry, cannot both claim the same
occurrence - and a worker that dies after claiming leaves that
occurrence unpaid rather than paid twice. For an instruction that moves
money with nobody watching, missing one is the mistake to prefer: the
customer sees an unpaid bill and pays it; a doubled payment they may
not see at all. The run then carries an Idempotency-Key of its own
(schedule id and occurrence), so even the saga's own retries can't
repeat it.

**Looked up before claiming.** Whose wallet it is and where the money
goes are read first. If a service can't answer, nothing is claimed and
the next tick tries again; only a definite answer - no such wallet, no
such recipient - uses the occurrence up, recorded as NOT_RUN with the
reason.

**An ordinary operation.** Each run is a transfer or a payment like one
made by hand: same saga, same balance, daily limit, card block and
fraud rules, same history, receipt and notification. A run that the
ledger refuses is a FAILED operation the customer is told about.

Runs are at a fixed hour (settings.autopay_hour_utc), on a weekday or a
day of the month from 1 to 28. A schedule whose time passed while the
service was down runs once when it is back, not once per missed day.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time, timedelta
from uuid import UUID

from fincore_common import DomainError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.scheduled_payment import ScheduledPayment, ScheduleInterval, ScheduleStatus
from app.domain.template import TemplateKind
from app.services import billers, ledger
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request
from app.services.parties import resolve_parties
from app.services.payments import CreatePaymentInput, create_payment
from app.services.recipients import find_recipient
from app.services.transfers import CreateTransferInput, create_transfer

logger = logging.getLogger(__name__)

NOT_RUN = "NOT_RUN"
_BATCH = 50


def next_run(interval: ScheduleInterval, day: int, *, after: datetime) -> datetime:
    """The first occurrence strictly after `after`: that weekday, or
    that day of the month, at the autopay hour (UTC)."""
    at = time(settings.autopay_hour_utc, tzinfo=UTC)
    candidate = after.astimezone(UTC).date()
    for _ in range(62):  # at most a month and a bit of days to look through
        moment = datetime.combine(candidate, at)
        fits = candidate.isoweekday() == day if interval is ScheduleInterval.WEEKLY else (
            candidate.day == day
        )
        if fits and moment > after:
            return moment
        candidate += timedelta(days=1)
    raise ValueError(f"no {interval.value} occurrence for day {day}")  # unreachable for valid input


@dataclass(frozen=True)
class _Plan:
    """What a run needs that had to be looked up, or why it can't run."""

    destination_wallet_id: UUID | None = None
    problem: str | None = None


class _TryLater(Exception):
    """A service couldn't answer: claim nothing, try again next tick."""


async def _plan(schedule: ScheduledPayment) -> _Plan:
    try:
        wallet = await ledger.ledger_client.find_wallet_owner(schedule.source_wallet_id)
    except ledger.LedgerUnavailableError as exc:
        raise _TryLater(str(exc)) from exc
    if (
        wallet is None
        or wallet.owner_user_id != schedule.owner_user_id
        or wallet.currency != schedule.currency
    ):
        return _Plan(problem="Wallet Not Found")

    if schedule.kind is TemplateKind.SERVICE:
        if billers.find(schedule.service_code or "") is None:
            return _Plan(problem="Service Not Found")
        return _Plan()

    try:
        recipient = await find_recipient(
            schedule.card_number or "", caller_user_id=schedule.owner_user_id
        )
    except DomainError as exc:
        # 503: the lookup couldn't be made. Anything else is an answer.
        if exc.status_code >= 500:
            raise _TryLater(exc.title) from exc
        return _Plan(problem=exc.title)
    if recipient.currency != schedule.currency:
        return _Plan(problem="Currency Mismatch")
    return _Plan(destination_wallet_id=recipient.wallet_id)


async def _claim(session: AsyncSession, schedule: ScheduledPayment, now: datetime) -> bool:
    """Moves the schedule on to its next occurrence, if nobody has yet."""
    result = await session.execute(
        update(ScheduledPayment)
        .where(
            ScheduledPayment.id == schedule.id,
            ScheduledPayment.status == ScheduleStatus.ACTIVE,
            ScheduledPayment.next_run_at == schedule.next_run_at,
        )
        .values(
            next_run_at=next_run(schedule.interval, schedule.day, after=now),
            last_run_at=now,
            # Until the run reports back.
            last_status="RUNNING",
            last_error=None,
            last_operation_id=None,
        )
    )
    await session.commit()
    return bool(result.rowcount)  # type: ignore[attr-defined]


async def _record(
    session: AsyncSession,
    schedule_id: UUID,
    *,
    status: str,
    error: str | None = None,
    operation_id: UUID | None = None,
) -> None:
    await session.execute(
        update(ScheduledPayment)
        .where(ScheduledPayment.id == schedule_id)
        .values(last_status=status, last_error=error, last_operation_id=operation_id)
    )
    await session.commit()


async def run_one(session: AsyncSession, schedule: ScheduledPayment, now: datetime) -> bool:
    """Makes one due run. Returns whether this call was the one to make
    it (False: someone else claimed it, or it has to wait)."""
    due = schedule.next_run_at
    try:
        plan = await _plan(schedule)
    except _TryLater as exc:
        logger.warning("autopay %s waits: %s", schedule.id, exc)
        return False
    if not await _claim(session, schedule, now):
        return False
    if plan.problem is not None:
        await _record(session, schedule.id, status=NOT_RUN, error=plan.problem)
        return True

    key = await begin_idempotent_request(
        session,
        user_id=schedule.owner_user_id,
        key=f"autopay:{schedule.id}:{due.isoformat()}",
        fingerprint=f"autopay:{schedule.id}",
    )
    operation_id: UUID
    status: str
    failure: str | None
    if schedule.kind is TemplateKind.SERVICE:
        biller = billers.find(schedule.service_code or "")
        assert biller is not None  # checked in _plan
        payment = await create_payment(
            session,
            CreatePaymentInput(
                initiator_user_id=schedule.owner_user_id,
                idempotency_key_id=key.id,
                source_wallet_id=schedule.source_wallet_id,
                merchant_id=biller.merchant_id,
                amount_minor=schedule.amount_minor,
                currency=schedule.currency,
                description=schedule.service_account,
                merchant_name=biller.name,
                merchant_owner_user_id=None,
                service_code=biller.code,
                service_account=schedule.service_account,
            ),
        )
        operation_id, status, failure = payment.id, payment.status.value, payment.failure_reason
    else:
        assert plan.destination_wallet_id is not None
        parties = await resolve_parties(
            initiator_user_id=schedule.owner_user_id,
            destination_wallet_id=plan.destination_wallet_id,
        )
        transfer = await create_transfer(
            session,
            CreateTransferInput(
                initiator_user_id=schedule.owner_user_id,
                idempotency_key_id=key.id,
                source_wallet_id=schedule.source_wallet_id,
                destination_wallet_id=plan.destination_wallet_id,
                amount_minor=schedule.amount_minor,
                currency=schedule.currency,
                description=schedule.name,
                recipient_user_id=parties.recipient_user_id,
                sender_name=parties.sender_name,
                recipient_name=parties.recipient_name,
                recipient_card_number=parties.recipient_card_number,
            ),
        )
        operation_id, status, failure = transfer.id, transfer.status.value, transfer.failure_reason
    await complete_idempotent_request(
        session, key, status_code=201, body={"id": str(operation_id)}, resource_id=operation_id
    )
    await _record(session, schedule.id, status=status, error=failure, operation_id=operation_id)
    return True


async def run_due(session: AsyncSession, *, now: datetime | None = None) -> int:
    """Makes every run that is due. Returns how many this call made."""
    moment = now or datetime.now(UTC)
    result = await session.execute(
        select(ScheduledPayment)
        .where(
            ScheduledPayment.status == ScheduleStatus.ACTIVE,
            ScheduledPayment.next_run_at <= moment,
        )
        .order_by(ScheduledPayment.next_run_at)
        .limit(_BATCH)
    )
    made = 0
    for schedule in result.scalars().all():
        try:
            if await run_one(session, schedule, moment):
                made += 1
        except Exception:
            # One schedule's trouble is not the others': it stays claimed
            # (at most once) and says RUNNING until its next run.
            logger.exception("autopay %s failed mid-run", schedule.id)
            await session.rollback()
    return made

