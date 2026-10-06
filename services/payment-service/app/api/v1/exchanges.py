from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AuthenticatedUser,
    get_authenticated_user,
    get_idempotency_fingerprint,
)
from app.core.amounts import parse_positive_amount
from app.core.exceptions import ExchangeNotFoundError
from app.db.session import get_db
from app.domain.exchange import Exchange, ExchangeStatus
from app.repositories.exchange_repository import ExchangeRepository
from app.services import exchanges
from app.services.exchanges import CreateExchangeInput, Quote, rate_text
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request

router = APIRouter(prefix="/api/v1/exchanges", tags=["exchanges"])


class QuoteResponse(BaseModel):
    source_amount_minor: int
    source_currency: str
    # What the source amount buys right now, rounded down to a whole
    # minor unit. Send it back as `expected_destination_amount_minor`.
    destination_amount_minor: int
    destination_currency: str
    # Units of the destination currency per one unit of the source, as
    # a decimal string.
    rate: str
    # When the rate provider last updated its rates.
    rate_updated_at: datetime

    @classmethod
    def of(cls, quote: Quote) -> "QuoteResponse":
        return cls(
            source_amount_minor=quote.source_amount_minor,
            source_currency=quote.source_currency,
            destination_amount_minor=quote.destination_amount_minor,
            destination_currency=quote.destination_currency,
            rate=rate_text(quote.rate),
            rate_updated_at=quote.rate_updated_at,
        )


class CreateExchangeRequest(BaseModel):
    # Both must be the caller's own wallets, in different currencies.
    source_wallet_id: UUID
    destination_wallet_id: UUID
    # How much of the source wallet's currency to sell; a decimal
    # string, never a JSON number (ADR-0001).
    amount: str = Field(min_length=1, max_length=32)
    # The `destination_amount_minor` of the quote the customer agreed
    # to. If the rate has moved and the amount would differ, nothing is
    # exchanged (409 Rate Changed).
    expected_destination_amount_minor: int = Field(gt=0)


class ExchangeResponse(BaseModel):
    id: UUID
    reference: str
    source_wallet_id: UUID
    destination_wallet_id: UUID
    source_amount_minor: int
    source_currency: str
    destination_amount_minor: int
    destination_currency: str
    rate: str
    # COMPLETED; FAILED (nothing was taken, or it was returned -
    # `failure_reason` says why); or PENDING / DEBITED / REVERSING while
    # it is still being carried out.
    status: ExchangeStatus
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def of(cls, exchange: Exchange) -> "ExchangeResponse":
        return cls(
            id=exchange.id,
            reference=exchange.reference,
            source_wallet_id=exchange.source_wallet_id,
            destination_wallet_id=exchange.destination_wallet_id,
            source_amount_minor=exchange.source_amount_minor,
            source_currency=exchange.source_currency,
            destination_amount_minor=exchange.destination_amount_minor,
            destination_currency=exchange.destination_currency,
            rate=rate_text(exchange.rate),
            status=exchange.status,
            failure_reason=exchange.failure_reason,
            created_at=exchange.created_at,
            completed_at=exchange.completed_at,
        )


@router.get("/quote", response_model=QuoteResponse)
async def get_quote(
    source_wallet_id: UUID = Query(...),
    destination_wallet_id: UUID = Query(...),
    amount: str = Query(..., min_length=1, max_length=32),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> QuoteResponse:
    """What `amount` of the source wallet's currency would buy in the
    destination wallet's currency right now. Moves nothing and promises
    nothing: the exchange itself checks the amount again."""
    source_currency, destination_currency = await exchanges.wallet_currencies(
        source_wallet_id, destination_wallet_id, bearer_token=user.access_token
    )
    amount_minor = parse_positive_amount(amount, source_currency)
    return QuoteResponse.of(
        await exchanges.quote(amount_minor, source_currency, destination_currency)
    )


@router.post("", response_model=ExchangeResponse, status_code=status.HTTP_201_CREATED)
async def create_exchange(
    payload: CreateExchangeRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> ExchangeResponse:
    """Exchanges money between two of the caller's own wallets at the
    current rate, with no fee. The source amount is taken first and the
    destination amount credited second; if the second step is refused
    the first is returned, so the customer never ends up without both.
    Needs an Idempotency-Key like any money movement."""
    source_currency, destination_currency = await exchanges.wallet_currencies(
        payload.source_wallet_id, payload.destination_wallet_id, bearer_token=user.access_token
    )
    amount_minor = parse_positive_amount(payload.amount, source_currency)
    current = await exchanges.quote(amount_minor, source_currency, destination_currency)
    exchanges.check_expected(current, payload.expected_destination_amount_minor)
    positions = await exchanges.position_accounts(source_currency, destination_currency)

    # Everything above can refuse without having taken the key or moved
    # anything; from here on a retry with the same key is a replay.
    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )
    exchange = await exchanges.create_exchange(
        session,
        CreateExchangeInput(
            initiator_user_id=user.user_id,
            idempotency_key_id=idempotency_key.id,
            source_wallet_id=payload.source_wallet_id,
            destination_wallet_id=payload.destination_wallet_id,
            quote=current,
        ),
        positions=positions,
    )

    response = ExchangeResponse.of(exchange)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_201_CREATED,
        body=jsonable_encoder(response),
        resource_id=exchange.id,
    )
    return response


@router.get("/{exchange_id}", response_model=ExchangeResponse)
async def get_exchange(
    exchange_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> ExchangeResponse:
    exchange = await ExchangeRepository(session).get(exchange_id)
    if exchange is None or exchange.initiator_user_id != user.user_id:
        raise ExchangeNotFoundError(str(exchange_id))
    return ExchangeResponse.of(exchange)
