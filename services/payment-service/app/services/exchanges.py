"""Exchanging money between a customer's own wallets in two currencies.

The ledger only knows single-currency postings, so an exchange is two
of them, each against FinCore's EXCHANGE account in that currency:

    sell:  DEBIT  customer's source wallet   CREDIT EXCHANGE (source currency)
    buy:   DEBIT  EXCHANGE (destination)     CREDIT customer's destination wallet

Two postings cannot be made atomically across two calls, so this is a
saga, ordered so that the customer never holds both sums: the source is
taken first, the destination given second. If the second step is
refused, the first is undone by a third posting (the sell reversed).
Every posting has its own idempotent `source_id` derived from the
exchange id, so any step can be repeated safely after a timeout - which
is what the recovery worker does with an exchange left mid-way.

    PENDING  --sell ok-->  DEBITED  --buy ok-->  COMPLETED
       |                      |
       | sell refused         | buy refused
       v                      v
     FAILED  <--reversal ok-- REVERSING
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from fincore_common import EventType, get_correlation_id
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AmountTooSmallError,
    ExchangeUnavailableError,
    RateChangedError,
    SameCurrencyExchangeError,
    WalletNotFoundError,
)
from app.core.metrics import EXCHANGES_TOTAL
from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.outbox import OutboxEvent
from app.repositories.exchange_repository import ExchangeRepository
from app.services import ledger, rates
from app.services.ledger import PostingOutcome

logger = logging.getLogger(__name__)

_SERVICE = "payment-service"


@dataclass(frozen=True)
class Quote:
    source_amount_minor: int
    source_currency: str
    destination_amount_minor: int
    destination_currency: str
    rate: Decimal
    rate_updated_at: datetime


def rate_text(rate: Decimal) -> str:
    """A rate as a plain decimal string (never exponent notation)."""
    return format(rate.quantize(Decimal("0.000000000000001")).normalize(), "f")


def _event(exchange: Exchange, event_type: EventType, status: ExchangeStatus) -> OutboxEvent:
    EXCHANGES_TOTAL.labels(status=status.value).inc()
    return OutboxEvent(
        aggregate_type="Exchange",
        aggregate_id=str(exchange.id),
        event_type=event_type.value,
        correlation_id=get_correlation_id(),
        payload={
            "exchange_id": str(exchange.id),
            "reference": exchange.reference,
            "initiator_user_id": str(exchange.initiator_user_id),
            "source_amount_minor": exchange.source_amount_minor,
            "source_currency": exchange.source_currency,
            "destination_amount_minor": exchange.destination_amount_minor,
            "destination_currency": exchange.destination_currency,
            "rate": rate_text(exchange.rate),
            "failure_reason": exchange.failure_reason,
            "status": status.value,
        },
    )


async def wallet_currencies(
    source_wallet_id: UUID, destination_wallet_id: UUID, *, bearer_token: str
) -> tuple[str, str]:
    """The currencies of two wallets that must both be the caller's own
    and differ in currency."""
    source = await ledger.ledger_client.get_wallet(source_wallet_id, user_bearer_token=bearer_token)
    if source is None:
        raise WalletNotFoundError(str(source_wallet_id))
    destination = await ledger.ledger_client.get_wallet(
        destination_wallet_id, user_bearer_token=bearer_token
    )
    if destination is None:
        raise WalletNotFoundError(str(destination_wallet_id))
    if source.currency == destination.currency:
        raise SameCurrencyExchangeError(
            f"both wallets are {source.currency}; an exchange is between two currencies"
        )
    return source.currency, destination.currency


async def quote(amount_minor: int, source_currency: str, destination_currency: str) -> Quote:
    """What `amount_minor` would buy right now."""
    try:
        current = await rates.current_rates()
        conversion = rates.convert(amount_minor, source_currency, destination_currency, current)
    except rates.RatesUnavailableError as exc:
        raise ExchangeUnavailableError(
            "Exchange rates aren't available right now. Try again shortly."
        ) from exc
    if conversion.destination_amount_minor <= 0:
        raise AmountTooSmallError(
            f"that is less than the smallest amount of {destination_currency}"
        )
    return Quote(
        source_amount_minor=amount_minor,
        source_currency=source_currency,
        destination_amount_minor=conversion.destination_amount_minor,
        destination_currency=destination_currency,
        rate=conversion.rate,
        rate_updated_at=current.updated_at,
    )


@dataclass(frozen=True)
class CreateExchangeInput:
    initiator_user_id: UUID
    idempotency_key_id: UUID
    source_wallet_id: UUID
    destination_wallet_id: UUID
    quote: Quote


async def position_accounts(source_currency: str, destination_currency: str) -> tuple[UUID, UUID]:
    """FinCore's EXCHANGE accounts for the two currencies. Asked for
    before anything is created or moved: without them there is nowhere
    to post to."""
    source = await ledger.ledger_client.get_system_account("EXCHANGE", source_currency)
    destination = await ledger.ledger_client.get_system_account("EXCHANGE", destination_currency)
    if source is None or destination is None:
        raise ExchangeUnavailableError("Exchange isn't available right now. Try again shortly.")
    return source, destination


def check_expected(current: Quote, expected_destination_amount_minor: int) -> None:
    """The customer agreed to a specific amount; they get exactly that
    or nothing."""
    if current.destination_amount_minor != expected_destination_amount_minor:
        raise RateChangedError(
            "The exchange rate changed. Check the new amount and confirm again."
        )


async def create_exchange(
    session: AsyncSession, data: CreateExchangeInput, *, positions: tuple[UUID, UUID]
) -> Exchange:
    """Records the exchange at the quoted rate and runs its saga as far
    as it will go now. Returns normally in every state: COMPLETED,
    FAILED (nothing lost), or still in progress if ledger-service did
    not answer - the recovery worker finishes those."""
    exchange = Exchange(
        initiator_user_id=data.initiator_user_id,
        source_wallet_id=data.source_wallet_id,
        destination_wallet_id=data.destination_wallet_id,
        source_position_account_id=positions[0],
        destination_position_account_id=positions[1],
        source_amount_minor=data.quote.source_amount_minor,
        source_currency=data.quote.source_currency,
        destination_amount_minor=data.quote.destination_amount_minor,
        destination_currency=data.quote.destination_currency,
        rate=data.quote.rate,
        idempotency_key_id=data.idempotency_key_id,
    )
    session.add(exchange)
    await session.commit()
    await session.refresh(exchange)
    return await advance(session, exchange)


async def _post(
    exchange: Exchange, step: str, currency: str, *, debit: UUID, credit: UUID, amount_minor: int
) -> ledger.PostingResult:
    return await ledger.ledger_client.create_posting(
        source_service=_SERVICE,
        source_id=f"{exchange.id}:{step}",
        type="EXCHANGE",
        currency=currency,
        entries=[
            {"account_id": str(debit), "direction": "DEBIT", "amount_minor": amount_minor},
            {"account_id": str(credit), "direction": "CREDIT", "amount_minor": amount_minor},
        ],
    )


async def advance(session: AsyncSession, exchange: Exchange) -> Exchange:
    """Continues the saga from wherever the exchange is, one step at a
    time, until it finishes or ledger-service gives no answer. Safe to
    call again at any point, by anyone: each posting is idempotent and
    each status change is an atomic compare-and-set."""
    repository = ExchangeRepository(session)

    while True:
        await session.refresh(exchange)

        if exchange.status == ExchangeStatus.PENDING:
            result = await _post(
                exchange,
                "sell",
                exchange.source_currency,
                debit=exchange.source_wallet_id,
                credit=exchange.source_position_account_id,
                amount_minor=exchange.source_amount_minor,
            )
            if result.outcome == PostingOutcome.UNKNOWN:
                return exchange
            if result.outcome == PostingOutcome.SUCCESS:
                await repository.transition(
                    exchange.id, expected=ExchangeStatus.PENDING, new_status=ExchangeStatus.DEBITED
                )
                await session.commit()
                continue
            # Refused (insufficient funds, a frozen wallet): nothing moved.
            exchange.failure_reason = result.failure_reason
            if await repository.transition(
                exchange.id,
                expected=ExchangeStatus.PENDING,
                new_status=ExchangeStatus.FAILED,
                failure_reason=result.failure_reason,
            ):
                session.add(_event(exchange, EventType.EXCHANGE_FAILED, ExchangeStatus.FAILED))
            await session.commit()
            continue

        if exchange.status == ExchangeStatus.DEBITED:
            result = await _post(
                exchange,
                "buy",
                exchange.destination_currency,
                debit=exchange.destination_position_account_id,
                credit=exchange.destination_wallet_id,
                amount_minor=exchange.destination_amount_minor,
            )
            if result.outcome == PostingOutcome.UNKNOWN:
                return exchange
            if result.outcome == PostingOutcome.SUCCESS:
                now = datetime.now(UTC)
                if await repository.transition(
                    exchange.id,
                    expected=ExchangeStatus.DEBITED,
                    new_status=ExchangeStatus.COMPLETED,
                    completed_at=now,
                ):
                    session.add(
                        _event(exchange, EventType.EXCHANGE_COMPLETED, ExchangeStatus.COMPLETED)
                    )
                await session.commit()
                continue
            # The destination wallet can't be credited (frozen, closed):
            # the customer's source money must go back.
            await repository.transition(
                exchange.id,
                expected=ExchangeStatus.DEBITED,
                new_status=ExchangeStatus.REVERSING,
                failure_reason=result.failure_reason,
            )
            await session.commit()
            continue

        if exchange.status == ExchangeStatus.REVERSING:
            result = await _post(
                exchange,
                "reverse",
                exchange.source_currency,
                debit=exchange.source_position_account_id,
                credit=exchange.source_wallet_id,
                amount_minor=exchange.source_amount_minor,
            )
            if result.outcome == PostingOutcome.SUCCESS:
                if await repository.transition(
                    exchange.id, expected=ExchangeStatus.REVERSING, new_status=ExchangeStatus.FAILED
                ):
                    session.add(_event(exchange, EventType.EXCHANGE_FAILED, ExchangeStatus.FAILED))
                await session.commit()
                continue
            if result.outcome == PostingOutcome.BUSINESS_REJECTION:
                # The customer's money is with FinCore and can't be put
                # back (their source wallet was frozen meanwhile). Left
                # REVERSING for the recovery worker to keep trying, and
                # loud: this needs a person if it persists.
                logger.error(
                    "exchange %s: reversal refused (%s); customer is owed %d %s",
                    exchange.id,
                    result.failure_reason,
                    exchange.source_amount_minor,
                    exchange.source_currency,
                )
            return exchange

        return exchange  # COMPLETED or FAILED
