from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fincore_common.money import minor_to_decimal
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AuthenticatedUser,
    get_authenticated_user,
    get_idempotency_fingerprint,
)
from app.api.v1.schemas import PaymentResponse
from app.core.amounts import parse_positive_amount
from app.core.exceptions import (
    AmountOutOfRangeError,
    CurrencyMismatchError,
    ServiceNotFoundError,
    WalletNotFoundError,
)
from app.db.session import get_db
from app.services import billers, ledger
from app.services.billers import AccountKind, Biller, Category
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request
from app.services.payments import CreatePaymentInput, create_payment

router = APIRouter(prefix="/api/v1/services", tags=["services"])


class ServiceResponse(BaseModel):
    # What to pay it by: POST /api/v1/services/{code}/payments.
    code: str
    category: Category
    name: str
    # What identifies the customer there: a phone number, an internet
    # login or a personal account number.
    account_kind: AccountKind
    currency: str
    min_amount_minor: int
    max_amount_minor: int

    @classmethod
    def of(cls, biller: Biller) -> "ServiceResponse":
        return cls(
            code=biller.code,
            category=biller.category,
            name=biller.name,
            account_kind=biller.account_kind,
            currency=biller.currency,
            min_amount_minor=biller.min_amount_minor,
            max_amount_minor=biller.max_amount_minor,
        )


class PayServiceRequest(BaseModel):
    source_wallet_id: UUID
    # The customer's account at the provider, as typed.
    account: str = Field(min_length=1, max_length=64)
    # Decimal string at the API boundary, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)


@router.get("", response_model=list[ServiceResponse])
async def list_services(
    _: AuthenticatedUser = Depends(get_authenticated_user),
) -> list[ServiceResponse]:
    """The service providers a customer can pay, in display order."""
    return [ServiceResponse.of(biller) for biller in billers.CATALOG]


@router.post(
    "/{code}/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED
)
async def pay_service(
    code: str,
    payload: PayServiceRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """Pays a service provider from one of the caller's wallets: a
    payment like any other (same saga, same history), to the provider's
    merchant, recorded with the account it was for. Same order as
    payments.py: authorize -> validate -> idempotency -> saga."""
    source_wallet = await ledger.ledger_client.get_wallet(
        payload.source_wallet_id, user_bearer_token=user.access_token
    )
    if source_wallet is None:
        raise WalletNotFoundError(str(payload.source_wallet_id))

    biller = billers.find(code)
    if biller is None:
        raise ServiceNotFoundError(code)
    if source_wallet.currency != biller.currency:
        raise CurrencyMismatchError(
            f"{biller.name} is paid in {biller.currency}; this wallet is {source_wallet.currency}"
        )
    amount_minor = parse_positive_amount(payload.amount, biller.currency)
    if not biller.min_amount_minor <= amount_minor <= biller.max_amount_minor:
        raise AmountOutOfRangeError(
            f"{biller.name} takes between "
            f"{minor_to_decimal(biller.min_amount_minor, biller.currency):,} and "
            f"{minor_to_decimal(biller.max_amount_minor, biller.currency):,} "
            f"{biller.currency} at a time"
        )
    account = billers.clean_account(biller, payload.account)

    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )

    payment = await create_payment(
        session,
        CreatePaymentInput(
            initiator_user_id=user.user_id,
            idempotency_key_id=idempotency_key.id,
            source_wallet_id=payload.source_wallet_id,
            merchant_id=biller.merchant_id,
            amount_minor=amount_minor,
            currency=biller.currency,
            # The note everything else shows (history, receipt, statement).
            description=account,
            merchant_name=biller.name,
            # Nobody to tell "a payment was received": FinCore owns it.
            merchant_owner_user_id=None,
            service_code=biller.code,
            service_account=account,
        ),
    )

    response = PaymentResponse.model_validate(payment)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_201_CREATED,
        body=jsonable_encoder(response),
        resource_id=payment.id,
    )
    return response
