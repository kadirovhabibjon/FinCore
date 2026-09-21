from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import TransactionResponse
from app.core.exceptions import TransactionNotFoundError
from app.db.session import get_db
from app.repositories.payment_repository import PaymentRepository
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
    newest first across *both* Transfer and Payment. Only ever the
    operations they *initiated* — the other side of a transfer or
    payment sees it via ledger-service's
    `GET /api/v1/wallets/{id}/entries` instead, which is scoped by
    wallet rather than by who started the operation.

    Merged and sorted in Python rather than a single SQL query, since
    Transfer and Payment are two separate tables (each operation type
    gets its own table, spec Section 7.1) — a reasonable v1 approach at
    this scale; a UNION query would be the next step if this list ever
    needs to paginate over a serious volume of rows.
    """
    fetch_count = limit + offset
    transfers = await TransferRepository(session).list_for_user(
        user.user_id, limit=fetch_count, offset=0
    )
    payments = await PaymentRepository(session).list_for_user(
        user.user_id, limit=fetch_count, offset=0
    )

    combined = [TransactionResponse.from_transfer(transfer) for transfer in transfers] + [
        TransactionResponse.from_payment(payment) for payment in payments
    ]
    combined.sort(key=lambda item: item.created_at, reverse=True)
    return combined[offset : offset + limit]


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    transfer = await TransferRepository(session).get(transaction_id)
    if transfer is not None and transfer.initiator_user_id == user.user_id:
        return TransactionResponse.from_transfer(transfer)

    payment = await PaymentRepository(session).get(transaction_id)
    if payment is not None and payment.initiator_user_id == user.user_id:
        return TransactionResponse.from_payment(payment)

    raise TransactionNotFoundError(str(transaction_id))
