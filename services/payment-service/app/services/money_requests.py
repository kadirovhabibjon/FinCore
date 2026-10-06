"""Asking another customer for money, and answering such a request.

A request moves nothing. Paying one creates an ordinary Transfer, so it
gets the same fraud check, ledger posting and idempotency as any other
transfer; the request only records which transfer that was.

The one thing a request must never allow is being paid twice. Paying
therefore starts with an atomic claim (PENDING -> PAYING): of two
payments started at the same moment, exactly one gets the row.
"""

import enum
import logging
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fincore_common import EventType, get_correlation_id
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.amounts import parse_positive_amount
from app.core.exceptions import (
    CannotRequestFromSelfError,
    CurrencyMismatchError,
    MoneyRequestNotFoundError,
    MoneyRequestNotOpenError,
    TooManyOpenRequestsError,
    WalletNotFoundError,
)
from app.domain.money_request import MoneyRequest, MoneyRequestStatus
from app.domain.outbox import OutboxEvent
from app.domain.transfer import Transfer, TransferStatus
from app.repositories.money_request_repository import MoneyRequestRepository
from app.repositories.transfer_repository import TransferRepository
from app.services import identity, ledger
from app.services.parties import resolve_parties
from app.services.recipients import display_name, find_recipient
from app.services.transfers import CreateTransferInput, create_transfer

logger = logging.getLogger(__name__)

# Unanswered requests one customer may have at a time, in total and to
# any one person: a request puts a notification in someone else's bell.
MAX_OPEN_REQUESTS = 20
MAX_OPEN_REQUESTS_PER_PAYER = 3
# A claim with no transfer behind it after this long was abandoned by a
# crash between the two steps; the request becomes payable again.
_CLAIM_TIMEOUT = timedelta(minutes=2)


class RequestState(enum.StrEnum):
    """What a customer sees."""

    PENDING = "PENDING"
    # Being paid: the transfer is in progress or waiting for review.
    PROCESSING = "PROCESSING"
    PAID = "PAID"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True)
class RequestView:
    request: MoneyRequest
    state: RequestState
    # Why the last attempt to pay it failed, when it did.
    last_failure: str | None = None


def _event(request: MoneyRequest, event_type: EventType, status: MoneyRequestStatus) -> OutboxEvent:
    # Whoever did it: the requester creates, the person asked declines.
    actor = (
        request.payer_user_id
        if event_type == EventType.MONEY_REQUEST_DECLINED
        else request.requester_user_id
    )
    return OutboxEvent(
        aggregate_type="MoneyRequest",
        aggregate_id=str(request.id),
        event_type=event_type.value,
        correlation_id=get_correlation_id(),
        payload={
            "request_id": str(request.id),
            "reference": request.reference,
            "requester_user_id": str(request.requester_user_id),
            "payer_user_id": str(request.payer_user_id),
            "actor_user_id": str(actor),
            "requester_name": request.requester_name,
            "payer_name": request.payer_name,
            "amount_minor": request.amount_minor,
            "currency": request.currency,
            "note": request.note,
            "status": status.value,
        },
    )


async def view(session: AsyncSession, request: MoneyRequest) -> RequestView:
    """The request as it stands now. A PAYING request is settled here
    from its transfer - PAID once that completed, PENDING again if it
    failed - and the settled status is stored, so this is where a
    transfer finishing later (a fraud review approved, a recovered
    ledger outcome) reaches the request.
    """
    if request.status != MoneyRequestStatus.PAYING:
        return RequestView(request, RequestState(request.status.value))

    repository = MoneyRequestRepository(session)
    transfer: Transfer | None = None
    if request.transfer_id is not None:
        transfer = await TransferRepository(session).get(request.transfer_id)

    if transfer is None:
        abandoned = await repository.transition(
            request.id,
            expected=MoneyRequestStatus.PAYING,
            new_status=MoneyRequestStatus.PENDING,
            stale_before=datetime.now(UTC) - _CLAIM_TIMEOUT,
        )
        if abandoned:
            await session.commit()
            await session.refresh(request)
            return RequestView(request, RequestState.PENDING)
        return RequestView(request, RequestState.PROCESSING)

    if transfer.status == TransferStatus.COMPLETED:
        new_status = MoneyRequestStatus.PAID
    elif transfer.status in (TransferStatus.FAILED, TransferStatus.CANCELLED):
        new_status = MoneyRequestStatus.PENDING
    else:
        return RequestView(request, RequestState.PROCESSING)

    await repository.transition(
        request.id, expected=MoneyRequestStatus.PAYING, new_status=new_status
    )
    await session.commit()
    await session.refresh(request)
    return RequestView(
        request,
        RequestState(request.status.value),
        last_failure=transfer.failure_reason if new_status == MoneyRequestStatus.PENDING else None,
    )


async def _own_wallet_currency(wallet_id: UUID, *, bearer_token: str) -> str:
    """The currency of a wallet that must be the caller's own."""
    wallet = await ledger.ledger_client.get_wallet(wallet_id, user_bearer_token=bearer_token)
    if wallet is None:
        raise WalletNotFoundError(str(wallet_id))
    return wallet.currency


async def _name_of(user_id: UUID) -> str | None:
    try:
        user = await identity.identity_client.get_user(user_id)
    except identity.IdentityUnavailableError as exc:
        logger.warning("requester name lookup failed: %s", exc)
        return None
    return display_name(user.first_name, user.last_name) if user else None


async def create_request(
    session: AsyncSession,
    *,
    requester_user_id: UUID,
    bearer_token: str,
    wallet_id: UUID,
    from_card_number: str,
    amount: str,
    note: str | None,
) -> MoneyRequest:
    """Asks the owner of `from_card_number` to send `amount` to the
    caller's `wallet_id`."""
    currency = await _own_wallet_currency(wallet_id, bearer_token=bearer_token)
    payer = await find_recipient(from_card_number, caller_user_id=requester_user_id)
    if payer.own or payer.owner_user_id is None:
        raise CannotRequestFromSelfError("that card is one of your own")
    if payer.currency != currency:
        raise CurrencyMismatchError(
            f"that card is a {payer.currency} wallet; ask for {payer.currency} "
            f"into your {payer.currency} wallet"
        )
    amount_minor = parse_positive_amount(amount, currency)

    repository = MoneyRequestRepository(session)
    if await repository.count_open(requester_user_id) >= MAX_OPEN_REQUESTS:
        raise TooManyOpenRequestsError(
            f"You have {MAX_OPEN_REQUESTS} requests waiting for an answer. Cancel one first."
        )
    already = await repository.count_open(requester_user_id, payer_user_id=payer.owner_user_id)
    if already >= MAX_OPEN_REQUESTS_PER_PAYER:
        raise TooManyOpenRequestsError(
            "This person already has several of your requests waiting for an answer."
        )

    request = MoneyRequest(
        requester_user_id=requester_user_id,
        requester_wallet_id=wallet_id,
        payer_user_id=payer.owner_user_id,
        requester_name=await _name_of(requester_user_id),
        payer_name=payer.display_name,
        amount_minor=amount_minor,
        currency=currency,
        note=note,
    )
    repository.add(request)
    await session.flush()
    session.add(_event(request, EventType.MONEY_REQUEST_CREATED, MoneyRequestStatus.PENDING))
    await session.commit()
    await session.refresh(request)
    return request


async def get_for_party(session: AsyncSession, request_id: UUID, user_id: UUID) -> MoneyRequest:
    request = await MoneyRequestRepository(session).get(request_id)
    if request is None or user_id not in (request.requester_user_id, request.payer_user_id):
        raise MoneyRequestNotFoundError(str(request_id))
    return request


async def claim_for_payment(
    session: AsyncSession, request: MoneyRequest, *, payer_user_id: UUID
) -> None:
    """Takes the request for one payment attempt, or raises: only the
    person asked may pay, and only a request nobody is already paying."""
    if request.payer_user_id != payer_user_id:
        raise MoneyRequestNotFoundError(str(request.id))
    current = await view(session, request)
    claimed = current.state == RequestState.PENDING and await MoneyRequestRepository(
        session
    ).transition(
        request.id,
        expected=MoneyRequestStatus.PENDING,
        new_status=MoneyRequestStatus.PAYING,
        transfer_id=None,
    )
    if not claimed:
        raise MoneyRequestNotOpenError(f"this request is {current.state.value.lower()}")
    await session.commit()
    await session.refresh(request)


async def pay_claimed_request(
    session: AsyncSession,
    request: MoneyRequest,
    *,
    source_wallet_id: UUID,
    idempotency_key_id: UUID,
) -> RequestView:
    """Runs the transfer for a request claimed by `claim_for_payment`
    and settles the request from how it ended."""
    parties = await resolve_parties(
        initiator_user_id=request.payer_user_id, destination_wallet_id=request.requester_wallet_id
    )
    transfer = await create_transfer(
        session,
        CreateTransferInput(
            initiator_user_id=request.payer_user_id,
            idempotency_key_id=idempotency_key_id,
            source_wallet_id=source_wallet_id,
            destination_wallet_id=request.requester_wallet_id,
            amount_minor=request.amount_minor,
            currency=request.currency,
            description=request.note or f"Request {request.reference}",
            # The request already knows who is on each side; the lookup
            # only adds what it doesn't (the card number).
            recipient_user_id=request.requester_user_id,
            sender_name=parties.sender_name or request.payer_name,
            recipient_name=parties.recipient_name or request.requester_name,
            recipient_card_number=parties.recipient_card_number,
        ),
    )
    await MoneyRequestRepository(session).transition(
        request.id,
        expected=MoneyRequestStatus.PAYING,
        new_status=MoneyRequestStatus.PAYING,
        transfer_id=transfer.id,
    )
    await session.commit()
    await session.refresh(request)
    return await view(session, request)


async def source_wallet_for(
    request: MoneyRequest, wallet_id: UUID, *, bearer_token: str
) -> None:
    """Checks the wallet a request would be paid from: the caller's own,
    in the request's currency."""
    currency = await _own_wallet_currency(wallet_id, bearer_token=bearer_token)
    if currency != request.currency:
        raise CurrencyMismatchError(
            f"the request is in {request.currency}, that wallet is {currency}"
        )


async def decline(session: AsyncSession, request: MoneyRequest, *, payer_user_id: UUID) -> None:
    if request.payer_user_id != payer_user_id:
        raise MoneyRequestNotFoundError(str(request.id))
    current = await view(session, request)
    declined = current.state == RequestState.PENDING and await MoneyRequestRepository(
        session
    ).transition(
        request.id, expected=MoneyRequestStatus.PENDING, new_status=MoneyRequestStatus.DECLINED
    )
    if not declined:
        raise MoneyRequestNotOpenError(f"this request is {current.state.value.lower()}")
    session.add(_event(request, EventType.MONEY_REQUEST_DECLINED, MoneyRequestStatus.DECLINED))
    await session.commit()
    await session.refresh(request)


async def cancel(session: AsyncSession, request: MoneyRequest, *, requester_user_id: UUID) -> None:
    if request.requester_user_id != requester_user_id:
        raise MoneyRequestNotFoundError(str(request.id))
    current = await view(session, request)
    cancelled = current.state == RequestState.PENDING and await MoneyRequestRepository(
        session
    ).transition(
        request.id, expected=MoneyRequestStatus.PENDING, new_status=MoneyRequestStatus.CANCELLED
    )
    if not cancelled:
        raise MoneyRequestNotOpenError(f"this request is {current.state.value.lower()}")
    await session.commit()
    await session.refresh(request)
