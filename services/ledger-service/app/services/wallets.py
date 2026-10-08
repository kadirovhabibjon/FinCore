from datetime import UTC, datetime
from uuid import UUID

from fincore_common import SUPPORTED_CURRENCIES, generate_card_number
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnsupportedCurrencyError, WalletAlreadyExistsError
from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance
from app.repositories.account_repository import AccountRepository

_CARD_NUMBER_INDEX = "uq_ledger_accounts_card_number"
_PRIMARY_INDEX = "uq_ledger_accounts_primary_per_owner"
_CARD_NUMBER_ATTEMPTS = 5


async def create_wallet(session: AsyncSession, user_id: UUID, currency: str) -> LedgerAccount:
    """Opens a wallet, atomically with its zero balance row (Section 6:
    one wallet per (user, currency) in v1 — enforced by the partial
    unique index in ADR-0002, this is only the friendly pre-check).
    """
    if currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(currency)

    # A customer's first wallet is their main one.
    first = not await AccountRepository(session).get_wallets_for_user(user_id)

    # A random 16-digit number can collide with an existing one; the
    # unique index is what notices, and a new number is drawn.
    for _ in range(_CARD_NUMBER_ATTEMPTS):
        account = LedgerAccount(
            kind=AccountKind.USER_WALLET,
            owner_user_id=user_id,
            currency=currency,
            card_number=generate_card_number(),
            is_primary=first,
        )
        session.add(account)
        try:
            await session.flush()  # assign account.id; also where the unique indexes fire
        except IntegrityError as exc:
            await session.rollback()
            if _CARD_NUMBER_INDEX in str(exc.orig):
                continue
            if _PRIMARY_INDEX in str(exc.orig):
                # Two "first" wallets opened at once: the other one won.
                first = False
                continue
            raise WalletAlreadyExistsError(f"user already has a {currency} wallet") from exc
        break
    else:
        raise RuntimeError("could not allocate a unique card number")

    session.add(AccountBalance(account_id=account.id, kind=AccountKind.USER_WALLET))
    await session.commit()
    await session.refresh(account)
    return account


def clean_name(name: str | None) -> str | None:
    """A wallet's name as stored: trimmed, inner whitespace collapsed,
    and nothing at all rather than an empty string."""
    return " ".join(name.split()) or None if name is not None else None


async def rename_wallet(
    session: AsyncSession, account: LedgerAccount, name: str | None
) -> LedgerAccount:
    account.name = clean_name(name)
    await session.commit()
    await session.refresh(account)
    return account


async def make_primary(session: AsyncSession, account: LedgerAccount) -> LedgerAccount:
    """Makes this the owner's main wallet in place of whichever was.

    The owner's wallets are locked first, so two such requests at once
    take turns instead of each clearing a flag the other is about to
    set. Then the old flag is cleared before the new one is set: a
    unique index is checked row by row, not at the end of a statement,
    so a single UPDATE flipping both could trip over itself depending
    on which row it reached first."""
    owned = (
        LedgerAccount.owner_user_id == account.owner_user_id,
        LedgerAccount.kind == AccountKind.USER_WALLET,
    )
    await session.execute(
        select(LedgerAccount.id).where(*owned).order_by(LedgerAccount.id).with_for_update()
    )
    await session.execute(
        update(LedgerAccount)
        .where(*owned, LedgerAccount.is_primary, LedgerAccount.id != account.id)
        .values(is_primary=False)
    )
    await session.execute(
        update(LedgerAccount).where(LedgerAccount.id == account.id).values(is_primary=True)
    )
    await session.commit()
    await session.refresh(account)
    return account


async def set_blocked(
    session: AsyncSession, account: LedgerAccount, blocked: bool
) -> LedgerAccount:
    """Blocks or unblocks a wallet at its owner's request. Repeating
    either changes nothing (the first block's time is kept)."""
    if blocked and account.blocked_at is None:
        account.blocked_at = datetime.now(UTC)
    elif not blocked:
        account.blocked_at = None
    await session.commit()
    await session.refresh(account)
    return account
