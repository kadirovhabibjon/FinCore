"""What happened on the platform lately, for the admin console's first
page: per currency and per day, how many operations were started, how
much money they moved, and how many failed.

* operations - transfers and merchant payments created that day
  (exchanges are counted on their own: a customer's own money changing
  currency moves nothing between people);
* volume - the amounts of those that went through (a completed
  transfer; a captured payment, whatever was refunded later);
* failed - those that ended FAILED, or EXPIRED waiting for review.

Days are calendar days in UTC, by when the operation was created.
"""

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exchange import Exchange
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import FraudDecision, Transfer, TransferStatus

_WENT_THROUGH = {
    TransferStatus.COMPLETED.value,
    PaymentStatus.SUCCESS.value,
    PaymentStatus.PARTIALLY_REFUNDED.value,
    PaymentStatus.REFUNDED.value,
}
_FAILED = {TransferStatus.FAILED.value, PaymentStatus.FAILED.value, PaymentStatus.EXPIRED.value}


@dataclass
class DayTotals:
    day: date
    transfers: int = 0
    payments: int = 0
    exchanges: int = 0
    failed: int = 0
    volume_minor: int = 0


@dataclass
class PlatformStats:
    days: list[date]
    # currency -> one entry per day, oldest first, zeros included.
    by_currency: dict[str, list[DayTotals]] = field(default_factory=dict)
    awaiting_review: int = 0


def day_keys(now: datetime, days: int) -> list[date]:
    today = now.astimezone(UTC).date()
    return [today - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


async def platform_stats(
    session: AsyncSession, *, days: int, now: datetime | None = None
) -> PlatformStats:
    keys = day_keys(now or datetime.now(UTC), days)
    since = datetime.combine(keys[0], datetime.min.time(), tzinfo=UTC)
    stats = PlatformStats(days=keys)

    def totals(currency: str, day: date) -> DayTotals | None:
        if day not in keys:
            return None
        per_day = stats.by_currency.setdefault(currency, [DayTotals(key) for key in keys])
        return per_day[keys.index(day)]

    def daily(model: Any, currency: Any, amount: Any, *group: Any) -> Any:
        day = func.date(func.timezone("UTC", model.created_at)).label("day")
        return (
            select(currency, day, *group, func.count(), func.coalesce(func.sum(amount), 0))
            .where(model.created_at >= since)
            .group_by(currency, day, *group)
        )

    for model, counter in ((Transfer, "transfers"), (Payment, "payments")):
        rows = await session.execute(daily(model, model.currency, model.amount_minor, model.status))
        for currency, day, status, count, amount in rows.all():
            entry = totals(currency, day)
            if entry is None:
                continue
            setattr(entry, counter, getattr(entry, counter) + count)
            if status.value in _WENT_THROUGH:
                entry.volume_minor += int(amount)
            elif status.value in _FAILED:
                entry.failed += count

    exchanged = await session.execute(
        daily(Exchange, Exchange.source_currency, Exchange.source_amount_minor)
    )
    for currency, day, count, _amount in exchanged.all():
        entry = totals(currency, day)
        if entry is not None:
            entry.exchanges += count

    for model, waiting in (
        (Transfer, Transfer.status == TransferStatus.PENDING),
        (Payment, Payment.status == PaymentStatus.CREATED),
    ):
        result = await session.execute(
            select(func.count())
            .select_from(model)
            .where(
                waiting,
                model.fraud_decision == FraudDecision.REVIEW,
                model.reviewed_at.is_(None),
            )
        )
        stats.awaiting_review += int(result.scalar_one())
    return stats
