from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.internal.schemas import MerchantOwnershipResponse
from app.core.auth import require_internal_service
from app.core.exceptions import MerchantNotFoundError
from app.db.session import get_db
from app.repositories.merchant_repository import MerchantRepository

router = APIRouter(
    prefix="/internal/v1/merchants",
    tags=["internal"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("/{merchant_id}", response_model=MerchantOwnershipResponse)
async def get_merchant(
    merchant_id: UUID, session: AsyncSession = Depends(get_db)
) -> MerchantOwnershipResponse:
    """Lets webhook-service verify a merchant's owner and status before
    registering a webhook endpoint for it, reusing this service's own
    merchants table instead of webhook-service duplicating it.
    """
    merchant = await MerchantRepository(session).get(merchant_id)
    if merchant is None:
        raise MerchantNotFoundError(str(merchant_id))
    return MerchantOwnershipResponse.model_validate(merchant)
