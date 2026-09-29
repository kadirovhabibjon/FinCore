from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import CreateMerchantRequest, MerchantResponse, PaymentResponse
from app.core.exceptions import MerchantNotFoundError
from app.db.session import get_db
from app.domain.merchant import Merchant
from app.repositories.merchant_repository import MerchantRepository
from app.repositories.payment_repository import PaymentRepository

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


async def _get_owned_merchant(
    merchant_id: UUID, owner_user_id: UUID, session: AsyncSession
) -> Merchant:
    merchant = await MerchantRepository(session).get(merchant_id)
    # Same anti-enumeration reasoning as WalletNotFoundError: "doesn't
    # exist" and "exists but isn't yours" get the same response.
    if merchant is None or merchant.owner_user_id != owner_user_id:
        raise MerchantNotFoundError(str(merchant_id))
    return merchant


@router.get("/{merchant_id}", response_model=MerchantResponse)
async def get_merchant(
    merchant_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> MerchantResponse:
    merchant = await _get_owned_merchant(merchant_id, user.user_id, session)
    return MerchantResponse.model_validate(merchant)


@router.get("/{merchant_id}/payments", response_model=list[PaymentResponse])
async def list_merchant_payments(
    merchant_id: UUID,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[PaymentResponse]:
    """Payments *received* by one of the caller's merchants, newest
    first. The merchant side's counterpart to `GET /api/v1/payments/{id}`
    (which only the payer can read), and how an owner finds the payment
    id that `POST /api/v1/payments/{id}/refunds` needs.
    """
    await _get_owned_merchant(merchant_id, user.user_id, session)
    payments = await PaymentRepository(session).list_for_merchant(
        merchant_id, limit=limit, offset=offset
    )
    return [PaymentResponse.model_validate(payment) for payment in payments]
