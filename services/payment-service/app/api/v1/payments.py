from uuid import UUID

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fincore_common import parse_decimal_string
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AuthenticatedUser,
    get_authenticated_user,
    get_idempotency_fingerprint,
)
from app.api.v1.schemas import (
    CreatePaymentRequest,
    CreateRefundRequest,
    PaymentResponse,
    RefundResponse,
)
from app.core.exceptions import (
    CurrencyMismatchError,
    InvalidAmountError,
    MerchantNotActiveError,
    MerchantNotFoundError,
    PaymentNotEligibleForRefundError,
    PaymentNotFoundError,
    RefundExceedsRemainingAmountError,
    WalletNotFoundError,
)
from app.db.session import get_db
from app.domain.merchant import MerchantStatus
from app.domain.payment import PaymentStatus
from app.repositories.merchant_repository import MerchantRepository
from app.repositories.payment_repository import PaymentRepository
from app.services import ledger
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request
from app.services.payments import CreatePaymentInput, create_payment
from app.services.refunds import CreateRefundInput, create_refund

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


@router.post("", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def post_payment(
    payload: CreatePaymentRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    """Spec Section 11's flow, in the same order transfers use: authorize
    -> validate -> idempotency check -> create + run the saga.
    """
    # Authorize: does this wallet belong to the caller? Same relay
    # pattern as transfers.py's post_transfer.
    source_wallet = await ledger.ledger_client.get_wallet(
        payload.source_wallet_id, user_bearer_token=user.access_token
    )
    if source_wallet is None:
        raise WalletNotFoundError(str(payload.source_wallet_id))

    # Validate the request.
    merchant = await MerchantRepository(session).get(payload.merchant_id)
    if merchant is None:
        raise MerchantNotFoundError(str(payload.merchant_id))
    if merchant.status != MerchantStatus.ACTIVE:
        raise MerchantNotActiveError(f"merchant is {merchant.status.value}")
    if source_wallet.currency != payload.currency:
        raise CurrencyMismatchError(
            f"source wallet is {source_wallet.currency}, request is {payload.currency}"
        )
    try:
        amount_minor = parse_decimal_string(payload.amount, payload.currency)
    except ValueError as exc:
        raise InvalidAmountError(str(exc)) from exc

    # Idempotency check.
    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )

    # Create the Payment and run the saga to its first stopping point.
    payment = await create_payment(
        session,
        CreatePaymentInput(
            initiator_user_id=user.user_id,
            idempotency_key_id=idempotency_key.id,
            source_wallet_id=payload.source_wallet_id,
            merchant_id=payload.merchant_id,
            amount_minor=amount_minor,
            currency=payload.currency,
            description=payload.description,
        ),
    )

    response = PaymentResponse.model_validate(payment)
    response_body = jsonable_encoder(response)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_201_CREATED,
        body=response_body,
        resource_id=payment.id,
    )
    return response


@router.get("/{payment_id}", response_model=PaymentResponse)
async def get_payment(
    payment_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> PaymentResponse:
    payment = await PaymentRepository(session).get(payment_id)
    # Same anti-enumeration reasoning as WalletNotFoundError: "doesn't
    # exist" and "exists but isn't yours" get the same response.
    if payment is None or payment.initiator_user_id != user.user_id:
        raise PaymentNotFoundError(str(payment_id))
    return PaymentResponse.model_validate(payment)


@router.post(
    "/{payment_id}/refunds", response_model=RefundResponse, status_code=status.HTTP_201_CREATED
)
async def post_refund(
    payment_id: UUID,
    payload: CreateRefundRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> RefundResponse:
    """Refunds are merchant-initiated (spec Section 11 doesn't say so
    explicitly, but a refund is a merchant deciding to give money back —
    the same real-world shape as every payment platform's own refund
    API), so the caller must own the merchant the payment was made to,
    not be the payer.
    """
    payment = await PaymentRepository(session).get(payment_id)
    if payment is None:
        raise PaymentNotFoundError(str(payment_id))

    merchant = await MerchantRepository(session).get(payment.merchant_id)
    # Same anti-enumeration reasoning as everywhere else: a payment that
    # exists but belongs to a merchant the caller doesn't own looks the
    # same as a payment that doesn't exist.
    if merchant is None or merchant.owner_user_id != user.user_id:
        raise PaymentNotFoundError(str(payment_id))

    if payment.status not in (PaymentStatus.SUCCESS, PaymentStatus.PARTIALLY_REFUNDED):
        raise PaymentNotEligibleForRefundError(
            f"payment is {payment.status.value}, not eligible for refund"
        )

    try:
        amount_minor = parse_decimal_string(payload.amount, payment.currency)
    except ValueError as exc:
        raise InvalidAmountError(str(exc)) from exc

    remaining = payment.amount_minor - payment.refunded_amount_minor
    if amount_minor > remaining:
        raise RefundExceedsRemainingAmountError(
            f"refund amount {amount_minor} exceeds remaining refundable amount {remaining}"
        )

    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )

    refund = await create_refund(
        session,
        CreateRefundInput(
            payment_id=payment.id,
            idempotency_key_id=idempotency_key.id,
            amount_minor=amount_minor,
            reason=payload.reason,
        ),
    )

    response = RefundResponse.model_validate(refund)
    response_body = jsonable_encoder(response)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_201_CREATED,
        body=response_body,
        resource_id=refund.id,
    )
    return response
