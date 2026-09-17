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
from app.api.v1.schemas import CreateTransferRequest, TransferResponse
from app.core.exceptions import (
    CurrencyMismatchError,
    InvalidAmountError,
    SameWalletTransferError,
    TransferNotFoundError,
    WalletNotFoundError,
)
from app.db.session import get_db
from app.repositories.transfer_repository import TransferRepository
from app.services import ledger
from app.services.idempotency import begin_idempotent_request, complete_idempotent_request
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
    try:
        amount_minor = parse_decimal_string(payload.amount, payload.currency)
    except ValueError as exc:
        raise InvalidAmountError(str(exc)) from exc

    # Idempotency check.
    key, fingerprint = idem
    idempotency_key = await begin_idempotent_request(
        session, user_id=user.user_id, key=key, fingerprint=fingerprint
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
