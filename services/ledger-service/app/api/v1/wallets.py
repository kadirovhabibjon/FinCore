from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user_id
from app.api.v1.schemas import LedgerEntryResponse, WalletCreateRequest, WalletResponse
from app.core.exceptions import WalletNotFoundError
from app.db.session import get_db
from app.domain.account import LedgerAccount
from app.domain.balance import AccountBalance
from app.repositories.account_repository import AccountRepository
from app.services.wallets import create_wallet

router = APIRouter(prefix="/api/v1/wallets", tags=["wallets"])


def _wallet_response(account: LedgerAccount, balance: AccountBalance) -> WalletResponse:
    return WalletResponse(
        id=account.id,
        currency=account.currency,
        status=account.status,
        created_at=account.created_at,
        balance_minor=balance.balance_minor,
        held_minor=balance.held_minor,
    )


async def _get_owned_wallet_or_404(
    session: AsyncSession, wallet_id: UUID, user_id: UUID
) -> LedgerAccount:
    account = await AccountRepository(session).get_wallet_by_id(wallet_id)
    # Same wording for "doesn't exist" and "exists but isn't yours" — see
    # WalletNotFoundError's docstring.
    if account is None or account.owner_user_id != user_id:
        raise WalletNotFoundError(str(wallet_id))
    return account


@router.post("", response_model=WalletResponse, status_code=status.HTTP_201_CREATED)
async def open_wallet(
    payload: WalletCreateRequest,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> WalletResponse:
    account = await create_wallet(session, user_id, payload.currency)
    balance = await session.get(AccountBalance, account.id)
    assert balance is not None  # created atomically with the account above
    return _wallet_response(account, balance)


@router.get("", response_model=list[WalletResponse])
async def list_my_wallets(
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[WalletResponse]:
    accounts = await AccountRepository(session).get_wallets_for_user(user_id)
    responses = []
    for account in accounts:
        balance = await session.get(AccountBalance, account.id)
        assert balance is not None
        responses.append(_wallet_response(account, balance))
    return responses


@router.get("/{wallet_id}", response_model=WalletResponse)
async def get_wallet(
    wallet_id: UUID,
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> WalletResponse:
    account = await _get_owned_wallet_or_404(session, wallet_id, user_id)
    balance = await session.get(AccountBalance, account.id)
    assert balance is not None
    return _wallet_response(account, balance)


@router.get("/{wallet_id}/entries", response_model=list[LedgerEntryResponse])
async def list_wallet_entries(
    wallet_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user_id: UUID = Depends(get_current_user_id),
    session: AsyncSession = Depends(get_db),
) -> list[LedgerEntryResponse]:
    await _get_owned_wallet_or_404(session, wallet_id, user_id)
    entries = await AccountRepository(session).get_entries_for_account(
        wallet_id, limit=limit, offset=offset
    )
    return [LedgerEntryResponse.model_validate(entry) for entry in entries]
