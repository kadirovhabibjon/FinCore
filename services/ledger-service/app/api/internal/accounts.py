from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import SystemAccountResponse
from app.core.auth import require_internal_service
from app.core.exceptions import UnknownAccountError
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
