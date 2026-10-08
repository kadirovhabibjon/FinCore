"""A customer's own daily sending limit on a wallet.

What counts: transfers sent and merchant payments made from the wallet
in the last 24 hours, unless they failed (a payment refunded later
still counts - the money did leave). Exchanges between the customer's
own wallets don't count: that money stays theirs.

A rolling 24 hours rather than a calendar day, so there is no midnight
at which the limit can be spent twice, and no time zone to pick.

An operation over the limit is recorded and failed, like one the ledger
refuses for insufficient funds, rather than rejected as a request: the
decision has to be made in the transaction that records the operation
(`fits`), which is after the request's idempotency key was taken - and
a check made before the key would also refuse the replay of a request
that itself used the limit up. Clients read the remaining amount first
(GET /api/v1/limits/{wallet_id}) and don't offer what won't fit.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.domain.wallet_limit import WalletLimit

WINDOW = timedelta(hours=24)
# The failure reason of an operation refused for this. Worded like the
# API's error titles, which is what the other failure reasons are.
OVER_LIMIT_REASON = "Daily Limit Exceeded"


@dataclass(frozen=True)
class LimitStatus:
    daily_limit_minor: int | None
    spent_minor: int

    @property
    def remaining_minor(self) -> int | None:
        if self.daily_limit_minor is None:
            return None
        return max(self.daily_limit_minor - self.spent_minor, 0)


async def spent_minor(session: AsyncSession, wallet_id: UUID) -> int:
    since = datetime.now(UTC) - WINDOW
    transfers = await session.execute(
        select(func.coalesce(func.sum(Transfer.amount_minor), 0)).where(
            Transfer.source_wallet_id == wallet_id,
            Transfer.created_at > since,
            Transfer.status != TransferStatus.FAILED,
        )
    )
    payments = await session.execute(
        select(func.coalesce(func.sum(Payment.amount_minor), 0)).where(
            Payment.source_wallet_id == wallet_id,
            Payment.created_at > since,
            Payment.status.notin_([PaymentStatus.FAILED, PaymentStatus.EXPIRED]),
        )
    )
    return int(transfers.scalar_one()) + int(payments.scalar_one())


async def get_status(session: AsyncSession, wallet_id: UUID) -> LimitStatus:
    limit = await session.get(WalletLimit, wallet_id)
    return LimitStatus(
        daily_limit_minor=limit.daily_limit_minor if limit else None,
        spent_minor=await spent_minor(session, wallet_id),
    )


async def set_limit(
    session: AsyncSession,
    *,
    wallet_id: UUID,
    owner_user_id: UUID,
    currency: str,
    daily_limit_minor: int | None,
) -> LimitStatus:
    """Sets, changes or (None) removes the limit. Takes effect for the
    next operation; lowering it below what was already sent today just
    means nothing more can be sent until enough of that is a day old."""
    limit = await session.get(WalletLimit, wallet_id)
    if daily_limit_minor is None:
        if limit is not None:
            await session.delete(limit)
    elif limit is None:
        session.add(
            WalletLimit(
                wallet_id=wallet_id,
                owner_user_id=owner_user_id,
                currency=currency,
                daily_limit_minor=daily_limit_minor,
            )
        )
    else:
        limit.daily_limit_minor = daily_limit_minor
    await session.commit()
    return await get_status(session, wallet_id)


async def fits(session: AsyncSession, wallet_id: UUID, amount_minor: int) -> bool:
    """Whether one more operation of this amount stays within the limit,
    decided so that concurrent operations on the same wallet cannot each
    be told yes: a transaction-scoped lock on the wallet is held from
    here until the caller commits the operation's own row, so the next
    one to ask already sees it. Call in the transaction that inserts the
    operation, before the insert."""
    limit = await session.get(WalletLimit, wallet_id)
    if limit is None:
        return True
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"wallet-limit:{wallet_id}"},
    )
    # Read again under the lock: it may have been changed while waiting.
    await session.refresh(limit)
    return await spent_minor(session, wallet_id) + amount_minor <= limit.daily_limit_minor
