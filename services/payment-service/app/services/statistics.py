"""Money in and money out per month, for the customer's statistics page.

What counts, and what deliberately does not:

* out - transfers the customer sent that completed, and payments that
  were captured, net of what was refunded;
* in  - transfers that reached the customer.

Exchanges are left out: they are the customer's own money changing
currency, neither earned nor spent. Top-ups are not operations of this
service, and a merchant's takings are on the merchant's own page.
Months are calendar months in UTC, by when the money moved.
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus

_CAPTURED = (PaymentStatus.SUCCESS, PaymentStatus.PARTIALLY_REFUNDED, PaymentStatus.REFUNDED)


@dataclass
class MonthTotals:
    month: str  # "2026-10"
    in_minor: int = 0
    out_minor: int = 0


def month_keys(now: datetime, months: int) -> list[str]:
    """The last `months` calendar months up to and including `now`'s,
    oldest first."""
    year, month = now.astimezone(UTC).year, now.astimezone(UTC).month
    keys: list[str] = []
    for _ in range(months):
        keys.append(f"{year:04d}-{month:02d}")
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    return keys[::-1]


def _first_instant(key: str) -> datetime:
    return datetime(int(key[:4]), int(key[5:7]), 1, tzinfo=UTC)


async def monthly_totals(
    session: AsyncSession, user_id: UUID, *, months: int, now: datetime | None = None
) -> dict[str, list[MonthTotals]]:
    """Per currency, one entry for each of the last `months` months
    (zeros included, so a chart has every month), oldest first. Only
    currencies with any movement in the period are returned."""
    keys = month_keys(now or datetime.now(UTC), months)
    since = _first_instant(keys[0])
    by_currency: dict[str, dict[str, MonthTotals]] = {}

    def add(currency: str, moment: datetime, *, received: int = 0, spent: int = 0) -> None:
        key = moment.astimezone(UTC).strftime("%Y-%m")
        if key not in keys:
            return
        months_of = by_currency.setdefault(currency, {k: MonthTotals(k) for k in keys})
        months_of[key].in_minor += received
        months_of[key].out_minor += spent

    def monthly(model: Any, moved_at: Any, amount: Any) -> Select[Any]:
        month = func.date_trunc("month", func.timezone("UTC", moved_at)).label("month")
        return select(model.currency, month, func.sum(amount)).group_by(model.currency, month)

    transfer_moved = func.coalesce(Transfer.completed_at, Transfer.updated_at)
    sent = await session.execute(
        monthly(Transfer, transfer_moved, Transfer.amount_minor).where(
            Transfer.initiator_user_id == user_id,
            Transfer.status == TransferStatus.COMPLETED,
            transfer_moved >= since,
        )
    )
    for currency, month, total in sent.all():
        add(currency, month.replace(tzinfo=UTC), spent=int(total))

    received = await session.execute(
        monthly(Transfer, transfer_moved, Transfer.amount_minor).where(
            Transfer.recipient_user_id == user_id,
            Transfer.status == TransferStatus.COMPLETED,
            transfer_moved >= since,
        )
    )
    for currency, month, total in received.all():
        add(currency, month.replace(tzinfo=UTC), received=int(total))

    payment_moved = func.coalesce(Payment.completed_at, Payment.updated_at)
    paid = await session.execute(
        monthly(
            Payment, payment_moved, Payment.amount_minor - Payment.refunded_amount_minor
        ).where(
            Payment.initiator_user_id == user_id,
            Payment.status.in_(_CAPTURED),
            payment_moved >= since,
        )
    )
    for currency, month, total in paid.all():
        add(currency, month.replace(tzinfo=UTC), spent=int(total))

    return {
        currency: [months_of[key] for key in keys]
        for currency, months_of in sorted(by_currency.items())
    }
