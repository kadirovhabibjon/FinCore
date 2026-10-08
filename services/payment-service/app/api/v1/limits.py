from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.core.amounts import parse_positive_amount
from app.core.exceptions import WalletNotFoundError
from app.db.session import get_db
from app.services import ledger, limits
from app.services.ledger import WalletInfo

router = APIRouter(prefix="/api/v1/limits", tags=["limits"])


class SetLimitRequest(BaseModel):
    # The most this wallet may send in any 24 hours, as a decimal string
    # in the wallet's currency; null removes the limit.
    daily_limit: str | None = Field(max_length=32)


class LimitResponse(BaseModel):
    wallet_id: UUID
    currency: str
    # Null: the owner has set no limit.
    daily_limit_minor: int | None
    # Sent from this wallet in the last 24 hours (transfers and merchant
    # payments that did not fail).
    spent_minor: int
    # What can still be sent now; null without a limit.
    remaining_minor: int | None
    window_hours: int


async def _owned_wallet(wallet_id: UUID, user: AuthenticatedUser) -> WalletInfo:
    # ledger-service decides whose wallet it is (see transfers.py).
    wallet = await ledger.ledger_client.get_wallet(wallet_id, user_bearer_token=user.access_token)
    if wallet is None:
        raise WalletNotFoundError(str(wallet_id))
    return wallet


def _response(wallet: WalletInfo, status: limits.LimitStatus) -> LimitResponse:
    return LimitResponse(
        wallet_id=wallet.id,
        currency=wallet.currency,
        daily_limit_minor=status.daily_limit_minor,
        spent_minor=status.spent_minor,
        remaining_minor=status.remaining_minor,
        window_hours=int(limits.WINDOW.total_seconds() // 3600),
    )


@router.get("/{wallet_id}", response_model=LimitResponse)
async def get_limit(
    wallet_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> LimitResponse:
    """The caller's own daily sending limit on one of their wallets, and
    how much of it the last 24 hours have used."""
    wallet = await _owned_wallet(wallet_id, user)
    return _response(wallet, await limits.get_status(session, wallet_id))


@router.put("/{wallet_id}", response_model=LimitResponse)
async def put_limit(
    wallet_id: UUID,
    payload: SetLimitRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> LimitResponse:
    """Sets, changes or (with null) removes the limit."""
    wallet = await _owned_wallet(wallet_id, user)
    daily_limit_minor = (
        None
        if payload.daily_limit is None
        else parse_positive_amount(payload.daily_limit, wallet.currency)
    )
    status = await limits.set_limit(
        session,
        wallet_id=wallet_id,
        owner_user_id=user.user_id,
        currency=wallet.currency,
        daily_limit_minor=daily_limit_minor,
    )
    return _response(wallet, status)
