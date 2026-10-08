from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import (
    AuthenticatedUser,
    get_authenticated_user,
    get_idempotency_fingerprint,
)
from app.api.v1.schemas import (
    CreateTransferRequest,
    RecentRecipientResponse,
    RecipientResponse,
    TransferResponse,
)
from app.core.amounts import parse_positive_amount
from app.core.exceptions import (
    CurrencyMismatchError,
    InvalidRecipientQueryError,
    SameWalletTransferError,
    TransferNotFoundError,
    WalletNotFoundError,
)
from app.db.session import get_db
from app.repositories.transfer_repository import TransferRepository
from app.services import ledger
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request
from app.services.parties import resolve_parties
from app.services.recipients import find_recipient, find_recipient_by_phone
from app.services.transfers import CreateTransferInput, create_transfer

router = APIRouter(prefix="/api/v1/transfers", tags=["transfers"])


@router.post("", response_model=TransferResponse, status_code=status.HTTP_201_CREATED)
async def post_transfer(
    payload: CreateTransferRequest,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    idem: tuple[str, str] = Depends(get_idempotency_fingerprint),
    session: AsyncSession = Depends(get_db),
) -> TransferResponse:
    """Spec Section 10.1's flow, in the order the spec states it:
    authorize -> validate -> idempotency check -> create + run the saga.
    """
    # Authorize: does this wallet belong to the caller? Relays the
    # caller's own bearer token to ledger-service's public wallet
    # endpoint, which already enforces ownership — see app/services/
    # ledger.py's LedgerClient.get_wallet docstring for why this isn't
    # duplicated here instead.
    source_wallet = await ledger.ledger_client.get_wallet(
        payload.source_wallet_id, user_bearer_token=user.access_token
    )
    if source_wallet is None:
        raise WalletNotFoundError(str(payload.source_wallet_id))

    # Validate the request.
    if payload.source_wallet_id == payload.destination_wallet_id:
        raise SameWalletTransferError("source and destination wallets must differ")
    if source_wallet.currency != payload.currency:
        raise CurrencyMismatchError(
            f"source wallet is {source_wallet.currency}, request is {payload.currency}"
        )
    amount_minor = parse_positive_amount(payload.amount, payload.currency)

    # Idempotency check.
    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
    )

    # Who is on each side, for the recipient's history and notification.
    # After the idempotency check, so a replayed request doesn't repeat
    # the lookups; never a reason to fail (app/services/parties.py).
    parties = await resolve_parties(
        initiator_user_id=user.user_id, destination_wallet_id=payload.destination_wallet_id
    )

    # Create the Transfer and run the saga to its first stopping point.
    transfer = await create_transfer(
        session,
        CreateTransferInput(
            initiator_user_id=user.user_id,
            idempotency_key_id=idempotency_key.id,
            source_wallet_id=payload.source_wallet_id,
            destination_wallet_id=payload.destination_wallet_id,
            amount_minor=amount_minor,
            currency=payload.currency,
            description=payload.description,
            recipient_user_id=parties.recipient_user_id,
            sender_name=parties.sender_name,
            recipient_name=parties.recipient_name,
            recipient_card_number=parties.recipient_card_number,
        ),
    )

    response = TransferResponse.model_validate(transfer)
    response_body = jsonable_encoder(response)
    await complete_idempotent_request(
        session,
        idempotency_key,
        status_code=status.HTTP_201_CREATED,
        body=response_body,
        resource_id=transfer.id,
    )
    return response


@router.get("/recipients", response_model=list[RecentRecipientResponse])
async def list_recent_recipients(
    limit: int = Query(default=8, ge=1, le=20),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[RecentRecipientResponse]:
    """The cards the caller has sent money to, most recent first, one
    entry per card - for choosing the same person again without typing
    16 digits. Only transfers that completed, and whose card is known.
    The name is the one recorded when the money was last sent; the Send
    page still looks the card up again before anything is sent."""
    recipients = await TransferRepository(session).list_recent_recipients(
        user.user_id, limit=limit
    )
    return [
        RecentRecipientResponse(
            card_number=transfer.recipient_card_number or "",
            display_name=transfer.recipient_name,
            currency=transfer.currency,
            last_sent_at=transfer.created_at,
        )
        for transfer in recipients
    ]


# Declared before /{transfer_id}, which would otherwise capture "recipient".
@router.get("/recipient", response_model=RecipientResponse)
async def get_recipient(
    card_number: str | None = Query(default=None, min_length=16, max_length=32),
    phone: str | None = Query(default=None, min_length=5, max_length=32),
    currency: str | None = Query(default=None, min_length=3, max_length=3),
    user: AuthenticatedUser = Depends(get_authenticated_user),
) -> RecipientResponse:
    """Who would receive a transfer: the wallet to send to, its
    currency, and the owner's first name and last initial. Found by
    `card_number`, or by `phone` and the `currency` being sent - a phone
    number leads to its owner's wallet in that currency. Signed-in
    customers only, and rate-limited at the gateway, since it turns a
    number into a name."""
    if card_number is not None and phone is None:
        recipient = await find_recipient(card_number, caller_user_id=user.user_id)
    elif phone is not None and card_number is None and currency is not None:
        recipient = await find_recipient_by_phone(phone, currency, caller_user_id=user.user_id)
    else:
        raise InvalidRecipientQueryError("pass card_number, or phone and currency")
    return RecipientResponse(
        wallet_id=recipient.wallet_id,
        currency=recipient.currency,
        display_name=recipient.display_name,
        own=recipient.own,
        card_last4=recipient.card_last4,
    )


@router.get("/{transfer_id}", response_model=TransferResponse)
async def get_transfer(
    transfer_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> TransferResponse:
    transfer = await TransferRepository(session).get(transfer_id)
    # Same anti-enumeration reasoning as WalletNotFoundError: "doesn't
    # exist" and "exists but isn't yours" get the same response.
    if transfer is None or transfer.initiator_user_id != user.user_id:
        raise TransferNotFoundError(str(transfer_id))
    return TransferResponse.model_validate(transfer)
