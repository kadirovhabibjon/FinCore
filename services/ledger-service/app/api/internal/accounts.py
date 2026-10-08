from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import SystemAccountResponse, WalletByCardResponse
from app.core.auth import require_internal_service
from app.core.exceptions import UnknownAccountError, WalletNotFoundError
from app.db.session import get_db
from app.domain.account import AccountKind
from app.repositories.account_repository import AccountRepository

router = APIRouter(
    prefix="/internal/v1/accounts",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("/system", response_model=SystemAccountResponse)
async def get_system_account(
    kind: AccountKind = Query(...),
    currency: str = Query(..., min_length=3, max_length=3),
    session: AsyncSession = Depends(get_db),
) -> SystemAccountResponse:
    """Lets a caller (payment-service, building a refund posting) look
    up the id of a pooled system account (e.g. MERCHANT_SETTLEMENT for
    a currency) without needing to know or store it itself — the same
    reason `capture_hold` looks this account up internally rather than
    requiring the caller to pass its id (app/services/holds.py).
    """
    account = await AccountRepository(session).get_system_account(kind, currency)
    if account is None:
        raise UnknownAccountError(f"no {kind.value} account for {currency}")
    return SystemAccountResponse.model_validate(account)


@router.get("/wallet-by-card", response_model=WalletByCardResponse)
async def get_wallet_by_card(
    card_number: str = Query(..., min_length=16, max_length=16, pattern=r"^[0-9]{16}$"),
    session: AsyncSession = Depends(get_db),
) -> WalletByCardResponse:
    """The wallet a card number belongs to, whatever its status: whether
    a frozen or closed wallet may receive money is the caller's rule."""
    account = await AccountRepository(session).get_wallet_by_card_number(card_number)
    if account is None:
        raise WalletNotFoundError("no wallet has this card number")
    return WalletByCardResponse.model_validate(account)


@router.get("/wallet-of/{user_id}", response_model=WalletByCardResponse)
async def get_wallet_of_user(
    user_id: UUID,
    currency: str = Query(..., min_length=3, max_length=3),
    session: AsyncSession = Depends(get_db),
) -> WalletByCardResponse:
    """A user's wallet in one currency (there is at most one), whatever
    its status - for payment-service, which sends money to a person
    found by their phone number."""
    wallets = await AccountRepository(session).get_wallets_for_user(user_id)
    for account in wallets:
        if account.currency == currency:
            return WalletByCardResponse.model_validate(account)
    raise WalletNotFoundError(f"this user has no {currency} wallet")


@router.get("/wallets/{wallet_id}", response_model=WalletByCardResponse)
async def get_wallet_owner(
    wallet_id: UUID, session: AsyncSession = Depends(get_db)
) -> WalletByCardResponse:
    """Whose wallet this is - for payment-service, which records the
    recipient of a transfer so they can be told about it."""
    account = await AccountRepository(session).get_wallet_by_id(wallet_id)
    if account is None:
        raise WalletNotFoundError(str(wallet_id))
    return WalletByCardResponse.model_validate(account)
