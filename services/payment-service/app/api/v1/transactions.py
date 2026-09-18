from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import TransactionResponse
from app.core.exceptions import TransactionNotFoundError
from app.db.session import get_db
from app.repositories.transfer_repository import TransferRepository

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionResponse])
async def list_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[TransactionResponse]:
    """The caller's own business-operation history (spec Section 20),
    newest first. Only ever the operations they *initiated* — the other
    side of a transfer sees it via ledger-service's
    `GET /api/v1/wallets/{id}/entries` instead, which is scoped by wallet
    rather than by who started the operation.

    Transfer is the only operation type today; a future Payment would
    be merged into this same list rather than requiring a second
    endpoint (see TransactionResponse.from_transfer).
    """
    transfers = await TransferRepository(session).list_for_user(
        user.user_id, limit=limit, offset=offset
    )
    return [TransactionResponse.from_transfer(transfer) for transfer in transfers]


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    transfer = await TransferRepository(session).get(transaction_id)
    if transfer is None or transfer.initiator_user_id != user.user_id:
        raise TransactionNotFoundError(str(transaction_id))
    return TransactionResponse.from_transfer(transfer)
