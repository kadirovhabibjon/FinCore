from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AccountNotActiveError,
    CaptureExceedsHoldError,
    CurrencyMismatchError,
    HoldExpiredError,
    HoldNotActiveError,
    HoldNotFoundError,
    InsufficientFundsError,
    InvalidAccountKindError,
    UnknownAccountError,
)
from app.domain.account import AccountKind, AccountStatus
from app.domain.hold import Hold, HoldStatus
from app.domain.posting import EntryDirection, Posting, PostingType
from app.repositories.account_repository import AccountRepository
from app.repositories.hold_repository import HoldRepository
from app.repositories.posting_repository import PostingRepository
from app.services.postings import EntryInput, create_posting


async def create_hold(
    session: AsyncSession,
    *,
    source_service: str,
    source_id: str,
    account_id: UUID,
    amount_minor: int,
    currency: str,
    ttl_seconds: int,
) -> Hold:
    """Reserves funds on a wallet without moving money (ADR-0002): only
    `held_minor` changes, no posting is created.
    """
    hold_repository = HoldRepository(session)
    existing = await hold_repository.get_by_source(source_service, source_id)
    if existing is not None:
        return existing

    account_repository = AccountRepository(session)
    accounts = await account_repository.get_accounts([account_id])
    account = accounts.get(account_id)
    if account is None:
        raise UnknownAccountError(str(account_id))
    if account.kind != AccountKind.USER_WALLET:
        raise InvalidAccountKindError("holds are only supported on USER_WALLET accounts")
    if account.currency != currency:
        raise CurrencyMismatchError(
            f"account {account_id} is {account.currency}, hold is {currency}"
        )
    if account.status != AccountStatus.ACTIVE:
        raise AccountNotActiveError(f"account {account_id} is {account.status.value}")

    balances = await account_repository.lock_balances([account_id])
    balance = balances[account_id]
    available = balance.balance_minor - balance.held_minor
    if available < amount_minor:
        raise InsufficientFundsError(f"account {account_id} has insufficient available balance")

    balance.held_minor += amount_minor

    hold = Hold(
        account_id=account_id,
        amount_minor=amount_minor,
        currency=currency,
        source_service=source_service,
        source_id=source_id,
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )
    session.add(hold)

    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await hold_repository.get_by_source(source_service, source_id)
        if existing is not None:
            return existing
        raise

    await session.refresh(hold)
    return hold


async def capture_hold(
    session: AsyncSession,
    hold_id: UUID,
    *,
    amount_minor: int,
    source_service: str,
    source_id: str,
) -> Posting:
    """Converts an active hold into a real posting: DEBIT the wallet for
    `amount_minor` (which may be less than the held amount — the
    remainder is released, not left as a smaller open hold, per
    ADR-0002), CREDIT the currency's MERCHANT_SETTLEMENT account.

    `held_minor` is decremented and `create_posting` is called within
    the same still-open session/transaction, so both land in the one
    commit `create_posting` issues — there is no separate commit for the
    held_minor change.
    """
    hold_repository = HoldRepository(session)
    hold = await hold_repository.get_locked(hold_id)
    if hold is None:
        raise HoldNotFoundError(str(hold_id))

    if hold.status != HoldStatus.ACTIVE:
        if hold.status == HoldStatus.CAPTURED:
            # Idempotent retry: create_posting's own idempotency check
            # will find and return the posting this capture already
            # produced, without moving money again.
            existing = await PostingRepository(session).get_by_source(
                source_service, source_id, PostingType.PAYMENT
            )
            if existing is not None:
                return existing
        raise HoldNotActiveError(f"hold is {hold.status.value}")

    if datetime.now(UTC) > hold.expires_at:
        await _expire_hold(session, hold)
        raise HoldExpiredError(str(hold_id))

    if amount_minor > hold.amount_minor:
        raise CaptureExceedsHoldError(
            f"capture amount {amount_minor} exceeds held amount {hold.amount_minor}"
        )

    account_repository = AccountRepository(session)
    balances = await account_repository.lock_balances([hold.account_id])
    balances[hold.account_id].held_minor -= hold.amount_minor

    merchant_account = await account_repository.get_system_account(
        AccountKind.MERCHANT_SETTLEMENT, hold.currency
    )
    if merchant_account is None:
        raise UnknownAccountError(f"no MERCHANT_SETTLEMENT account for {hold.currency}")

    hold.status = HoldStatus.CAPTURED
    hold.resolved_at = datetime.now(UTC)

    return await create_posting(
        session,
        source_service=source_service,
        source_id=source_id,
        type=PostingType.PAYMENT,
        currency=hold.currency,
        entries=[
            EntryInput(hold.account_id, EntryDirection.DEBIT, amount_minor),
            EntryInput(merchant_account.id, EntryDirection.CREDIT, amount_minor),
        ],
    )


async def release_hold(session: AsyncSession, hold_id: UUID) -> Hold:
    hold_repository = HoldRepository(session)
    hold = await hold_repository.get_locked(hold_id)
    if hold is None:
        raise HoldNotFoundError(str(hold_id))

    if hold.status != HoldStatus.ACTIVE:
        # Idempotent: releasing an already-resolved hold (released,
        # captured, or expired) succeeds without changing anything —
        # same reasoning as identity-service's logout.
        return hold

    account_repository = AccountRepository(session)
    balances = await account_repository.lock_balances([hold.account_id])
    balances[hold.account_id].held_minor -= hold.amount_minor

    hold.status = HoldStatus.RELEASED
    hold.resolved_at = datetime.now(UTC)

    await session.commit()
    await session.refresh(hold)
    return hold


async def _expire_hold(session: AsyncSession, hold: Hold) -> None:
    """Lazy expiry: an ACTIVE hold past its expires_at is expired the
    moment something (here, a capture attempt) notices, rather than
    requiring a background sweeper to exist before holds work at all. A
    periodic job that proactively expires *unnoticed* holds is future
    work — the spec's reconciliation job is the natural place for it.
    """
    account_repository = AccountRepository(session)
    balances = await account_repository.lock_balances([hold.account_id])
    balances[hold.account_id].held_minor -= hold.amount_minor
    hold.status = HoldStatus.EXPIRED
    hold.resolved_at = datetime.now(UTC)
    await session.commit()
