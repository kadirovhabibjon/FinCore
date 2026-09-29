from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, require_roles
from app.api.v1.schemas import (
    AdminTransactionResponse,
    ReviewDecisionRequest,
    TransactionType,
)
from app.db.session import get_db
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.repositories.payment_repository import PaymentRepository
from app.repositories.transfer_repository import TransferRepository
from app.services.reviews import resolve_review

# ADR-0005's support/admin panel, same split as identity-service's admin
# API: SUPPORT and ADMIN can look, only ADMIN can decide.
router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_staff = require_roles("SUPPORT", "ADMIN")
_admin = require_roles("ADMIN")


@router.get("/reviews", response_model=list[AdminTransactionResponse])
async def list_reviews(
    limit: int = Query(default=100, ge=1, le=500),
    _: AuthenticatedUser = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[AdminTransactionResponse]:
    """Transfers and payments whose fraud check returned REVIEW and that
    nobody has decided on yet, oldest first. A payment left here past
    `payment_review_ttl_seconds` is expired by the expiration worker and
    drops out of the queue.
    """
    transfers = await TransferRepository(session).list_awaiting_review(limit=limit)
    payments = await PaymentRepository(session).list_awaiting_review(limit=limit)
    queue: list[Transfer | Payment] = [*transfers, *payments]
    queue.sort(key=lambda operation: operation.created_at)
    return [AdminTransactionResponse.from_operation(operation) for operation in queue[:limit]]


@router.post("/reviews/{operation_id}", response_model=AdminTransactionResponse)
async def decide_review(
    operation_id: UUID,
    payload: ReviewDecisionRequest,
    reviewer: AuthenticatedUser = Depends(_admin),
    session: AsyncSession = Depends(get_db),
) -> AdminTransactionResponse:
    """APPROVE runs the rest of the saga synchronously, so the response
    already shows where it landed (COMPLETED/SUCCESS, FAILED, or
    PROCESSING on an unknown ledger outcome); REJECT fails it.
    """
    operation = await resolve_review(
        session,
        operation_id=operation_id,
        reviewer_id=reviewer.user_id,
        decision=payload.decision,
    )
    return AdminTransactionResponse.from_operation(operation)


@router.get("/transactions", response_model=list[AdminTransactionResponse])
async def list_all_transactions(
    type: TransactionType | None = Query(default=None),
    status: str | None = Query(default=None, max_length=32),
    user_id: UUID | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: AuthenticatedUser = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> list[AdminTransactionResponse]:
    """Every user's transfers and payments, newest first. `status` is
    matched against each type's own state machine, so e.g. SUCCESS only
    ever matches payments and COMPLETED only transfers. Merged in Python
    the same way the user-facing `GET /api/v1/transactions` is.
    """
    fetch_count = limit + offset
    operations: list[Transfer | Payment] = []

    if type in (None, TransactionType.TRANSFER) and (
        status is None or status in TransferStatus.__members__
    ):
        operations += await TransferRepository(session).list_all(
            status=TransferStatus(status) if status else None,
            user_id=user_id,
            limit=fetch_count,
            offset=0,
        )
    if type in (None, TransactionType.PAYMENT) and (
        status is None or status in PaymentStatus.__members__
    ):
        operations += await PaymentRepository(session).list_all(
            status=PaymentStatus(status) if status else None,
            user_id=user_id,
            limit=fetch_count,
            offset=0,
        )

    operations.sort(key=lambda operation: operation.created_at, reverse=True)
    return [
        AdminTransactionResponse.from_operation(operation)
        for operation in operations[offset : offset + limit]
    ]
