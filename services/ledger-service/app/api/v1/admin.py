from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import require_roles
from app.api.v1.schemas import WalletResponse
from app.api.v1.wallets import _wallet_response
from app.db.session import get_db
from app.domain.balance import AccountBalance
from app.repositories.account_repository import AccountRepository

# The support/admin console (ADR-0005): staff can look, nothing here
# changes anything.
router = APIRouter(prefix="/api/v1/admin/wallets", tags=["admin"])

_staff = require_roles("SUPPORT", "ADMIN")


@router.get("", response_model=list[WalletResponse])
async def list_wallets_of_user(
    user_id: UUID = Query(...),
    _: UUID = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[WalletResponse]:
    """One customer's wallets with their balances, the main one first -
    what the customer sees on their own wallets page. SUPPORT and ADMIN.
    Read-only: staff cannot move, block or rename anything here."""
    accounts = await AccountRepository(session).get_wallets_for_user(user_id)
    responses = []
    for account in accounts:
        balance = await session.get(AccountBalance, account.id)
        assert balance is not None  # created atomically with the account
        responses.append(_wallet_response(account, balance))
    return responses
