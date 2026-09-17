from uuid import UUID

from fincore_common import SUPPORTED_CURRENCIES
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnsupportedCurrencyError, WalletAlreadyExistsError
from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance


async def create_wallet(session: AsyncSession, user_id: UUID, currency: str) -> LedgerAccount:
    """Opens a wallet, atomically with its zero balance row (Section 6:
    one wallet per (user, currency) in v1 — enforced by the partial
    unique index in ADR-0002, this is only the friendly pre-check).
    """
    if currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(currency)

    account = LedgerAccount(kind=AccountKind.USER_WALLET, owner_user_id=user_id, currency=currency)
    session.add(account)

    try:
        await session.flush()  # assign account.id; also where the unique index fires
    except IntegrityError as exc:
        await session.rollback()
        raise WalletAlreadyExistsError(f"user already has a {currency} wallet") from exc

    session.add(AccountBalance(account_id=account.id, kind=AccountKind.USER_WALLET))
    await session.commit()
    await session.refresh(account)
    return account
