from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import CreateMerchantRequest, MerchantResponse
from app.core.exceptions import MerchantNotFoundError
from app.db.session import get_db
from app.domain.merchant import Merchant
from app.repositories.merchant_repository import MerchantRepository

router = APIRouter(prefix="/api/v1/merchants", tags=["merchants"])


@router.post("", response_model=MerchantResponse, status_code=status.HTTP_201_CREATED)
async def create_merchant(
    payload: CreateMerchantRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> MerchantResponse:
    merchant = Merchant(owner_user_id=user.user_id, name=payload.name)
    session.add(merchant)
    await session.commit()
    await session.refresh(merchant)
    return MerchantResponse.model_validate(merchant)


@router.get("", response_model=list[MerchantResponse])
async def list_my_merchants(
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[MerchantResponse]:
    merchants = await MerchantRepository(session).list_for_owner(user.user_id)
    return [MerchantResponse.model_validate(merchant) for merchant in merchants]


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> MerchantResponse:
    merchant = await MerchantRepository(session).get(merchant_id)
    # Same anti-enumeration reasoning as WalletNotFoundError: "doesn't
    # exist" and "exists but isn't yours" get the same response.
    if merchant is None or merchant.owner_user_id != user.user_id:
        raise MerchantNotFoundError(str(merchant_id))
    return MerchantResponse.model_validate(merchant)
