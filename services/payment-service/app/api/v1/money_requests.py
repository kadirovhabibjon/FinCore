import enum
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AuthenticatedUser,
    get_authenticated_user,
    get_idempotency_fingerprint,
)
from app.core.exceptions import MoneyRequestNotOpenError
from app.db.session import get_db
from app.repositories.money_request_repository import MoneyRequestRepository
from app.services import money_requests
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request
from app.services.money_requests import RequestState, RequestView

router = APIRouter(prefix="/api/v1/money-requests", tags=["money-requests"])


class RequestDirection(enum.StrEnum):
    # Someone asks the caller for money.
    INCOMING = "INCOMING"
    # The caller asked someone.
    OUTGOING = "OUTGOING"


class CreateMoneyRequest(BaseModel):
    # The caller's wallet the money should arrive in.
    wallet_id: UUID
    # The card of the person being asked (16 digits; spaces allowed).
    from_card_number: str = Field(min_length=16, max_length=32)
    # Decimal string, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)
    note: str | None = Field(default=None, max_length=255)

    @field_validator("note")
    @classmethod
    def _blank_is_none(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class PayMoneyRequest(BaseModel):
    # The caller's wallet to pay from; must be in the request's currency.
    source_wallet_id: UUID


class MoneyRequestResponse(BaseModel):
    id: UUID
    reference: str
    direction: RequestDirection
    status: RequestState
    amount_minor: int
    currency: str
    note: str | None
    # The other person, as "First L.": who is asked (OUTGOING) or who
    # asks (INCOMING). Null when unknown.
    counterparty_name: str | None
    # The transfer paying it, once one was started.
    transfer_id: UUID | None
    # Why the last attempt to pay failed, if it did; the request is
    # PENDING again and can be paid once more.
    last_failure: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, shown: RequestView, *, viewer_user_id: UUID) -> "MoneyRequestResponse":
        request = shown.request
        incoming = request.payer_user_id == viewer_user_id
        return cls(
            id=request.id,
            reference=request.reference,
            direction=RequestDirection.INCOMING if incoming else RequestDirection.OUTGOING,
            status=shown.state,
            amount_minor=request.amount_minor,
            currency=request.currency,
            note=request.note,
            counterparty_name=request.requester_name if incoming else request.payer_name,
            transfer_id=request.transfer_id,
            last_failure=shown.last_failure,
            created_at=request.created_at,
            updated_at=request.updated_at,
        )


@router.post("", response_model=MoneyRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_money_request(
    payload: CreateMoneyRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> MoneyRequestResponse:
    """Asks the owner of a card to send the caller money. Nothing moves
    until that person pays; they are notified and can pay or decline.
    The card must belong to someone else and be in the same currency as
    the wallet the money should arrive in. A customer may have 20
    unanswered requests, 3 to any one person."""
    request = await money_requests.create_request(
        session,
        requester_user_id=user.user_id,
        bearer_token=user.access_token,
        wallet_id=payload.wallet_id,
        from_card_number=payload.from_card_number,
        amount=payload.amount,
        note=payload.note,
    )
    return MoneyRequestResponse.of(
        RequestView(request, RequestState.PENDING), viewer_user_id=user.user_id
    )


@router.get("", response_model=list[MoneyRequestResponse])
async def list_money_requests(
    limit: int = Query(default=50, ge=1, le=100),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[MoneyRequestResponse]:
    """Requests the caller made (OUTGOING) and requests made to the
    caller (INCOMING), newest first."""
    requests = await MoneyRequestRepository(session).list_for_user(user.user_id, limit=limit)
    return [
        MoneyRequestResponse.of(
            await money_requests.view(session, request), viewer_user_id=user.user_id
        )
        for request in requests
    ]


@router.post("/{request_id}/pay", response_model=MoneyRequestResponse)
async def pay_money_request(
    request_id: UUID,
    payload: PayMoneyRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> MoneyRequestResponse:
    """Pays a request made to the caller, as an ordinary transfer from
    `source_wallet_id` (fraud check, ledger posting and all). Needs an
    Idempotency-Key like any money movement. The result's `status` says
    how it went: PAID, PROCESSING (in progress or waiting for review),
    or PENDING again with `last_failure` if the transfer failed. A
    request can be paid once: a second payment gets 409."""
    request = await money_requests.get_for_party(session, request_id, user.user_id)
    await money_requests.source_wallet_for(
        request, payload.source_wallet_id, bearer_token=user.access_token
    )

    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )
    try:
        await money_requests.claim_for_payment(session, request, payer_user_id=user.user_id)
    except MoneyRequestNotOpenError:
        # Nothing was attempted under this key: free it, so the same key
        # isn't left "in progress" for a request that can't be paid.
        await session.delete(idempotency_key)
        await session.commit()
        raise
    shown = await money_requests.pay_claimed_request(
        session,
        request,
        source_wallet_id=payload.source_wallet_id,
        idempotency_key_id=idempotency_key.id,
    )

    response = MoneyRequestResponse.of(shown, viewer_user_id=user.user_id)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_200_OK,
        body=jsonable_encoder(response),
        resource_id=request.id,
    )
    return response


@router.post("/{request_id}/decline", response_model=MoneyRequestResponse)
async def decline_money_request(
    request_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> MoneyRequestResponse:
    """The person asked says no. The requester is notified."""
    request = await money_requests.get_for_party(session, request_id, user.user_id)
    await money_requests.decline(session, request, payer_user_id=user.user_id)
    return MoneyRequestResponse.of(
        await money_requests.view(session, request), viewer_user_id=user.user_id
    )


@router.post("/{request_id}/cancel", response_model=MoneyRequestResponse)
async def cancel_money_request(
    request_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> MoneyRequestResponse:
    """The requester withdraws a request nobody has answered yet."""
    request = await money_requests.get_for_party(session, request_id, user.user_id)
    await money_requests.cancel(session, request, requester_user_id=user.user_id)
    return MoneyRequestResponse.of(
        await money_requests.view(session, request), viewer_user_id=user.user_id
    )
