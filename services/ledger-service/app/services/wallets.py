from uuid import UUID

from fincore_common import SUPPORTED_CURRENCIES, generate_card_number
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import UnsupportedCurrencyError, WalletAlreadyExistsError
from app.domain.account import AccountKind, LedgerAccount
from app.domain.balance import AccountBalance

_CARD_NUMBER_INDEX = "uq_ledger_accounts_card_number"
_CARD_NUMBER_ATTEMPTS = 5


async def create_wallet(session: AsyncSession, user_id: UUID, currency: str) -> LedgerAccount:
    """Opens a wallet, atomically with its zero balance row (Section 6:
    one wallet per (user, currency) in v1 — enforced by the partial
    unique index in ADR-0002, this is only the friendly pre-check).
    """
    if currency not in SUPPORTED_CURRENCIES:
        raise UnsupportedCurrencyError(currency)

    # A random 16-digit number can collide with an existing one; the
    # unique index is what notices, and a new number is drawn.
    for _ in range(_CARD_NUMBER_ATTEMPTS):
        account = LedgerAccount(
            kind=AccountKind.USER_WALLET,
            owner_user_id=user_id,
            currency=currency,
            card_number=generate_card_number(),
        )
        session.add(account)
        try:
            await session.flush()  # assign account.id; also where the unique indexes fire
        except IntegrityError as exc:
            await session.rollback()
            if _CARD_NUMBER_INDEX in str(exc.orig):
                continue
            raise WalletAlreadyExistsError(f"user already has a {currency} wallet") from exc
        break
    else:
        raise RuntimeError("could not allocate a unique card number")

    session.add(AccountBalance(account_id=account.id, kind=AccountKind.USER_WALLET))
    await session.commit()
    await session.refresh(account)
    return account
