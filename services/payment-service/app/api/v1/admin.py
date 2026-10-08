from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, require_roles
from app.api.v1.schemas import (
    AdminTransactionResponse,
    ReviewDecisionRequest,
    TransactionType,
)
from app.db.session import get_db
from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.repositories.exchange_repository import UNFINISHED, ExchangeRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.transfer_repository import TransferRepository
from app.services import admin_stats, receipts
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


# What an exchange's own states are called in the console: the customer-
# facing names (`TransactionResponse.from_exchange`), since the saga's
# intermediate steps are one thing to anyone looking at it.
_EXCHANGE_STATUSES: dict[str, tuple[ExchangeStatus, ...]] = {
    "COMPLETED": (ExchangeStatus.COMPLETED,),
    "FAILED": (ExchangeStatus.FAILED,),
    "PROCESSING": UNFINISHED,
}

Operation = Transfer | Payment | Exchange


async def _operations(
    session: AsyncSession,
    *,
    type: TransactionType | None,
    status: str | None,
    user_id: UUID | None,
    count: int,
) -> list[Operation]:
    """The newest `count` operations matching the filters, newest first.
    `status` is matched against each type's own state machine, so e.g.
    SUCCESS only ever matches payments and PENDING only transfers.
    Merged in Python the same way the user-facing history is."""
    operations: list[Operation] = []

    if type in (None, TransactionType.TRANSFER) and (
        status is None or status in TransferStatus.__members__
    ):
        operations += await TransferRepository(session).list_all(
            status=TransferStatus(status) if status else None,
            user_id=user_id,
            limit=count,
            offset=0,
        )
    if type in (None, TransactionType.PAYMENT) and (
        status is None or status in PaymentStatus.__members__
    ):
        operations += await PaymentRepository(session).list_all(
            status=PaymentStatus(status) if status else None,
            user_id=user_id,
            limit=count,
            offset=0,
        )
    if type in (None, TransactionType.EXCHANGE) and (
        status is None or status in _EXCHANGE_STATUSES
    ):
        operations += await ExchangeRepository(session).list_all(
            statuses=_EXCHANGE_STATUSES[status] if status else None,
            user_id=user_id,
            limit=count,
            offset=0,
        )

    operations.sort(key=lambda operation: operation.created_at, reverse=True)
    return operations[:count]


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
    """Every user's transfers, payments and currency exchanges, newest
    first, optionally only one type, one status or one user's."""
    operations = await _operations(
        session, type=type, status=status, user_id=user_id, count=limit + offset
    )
    return [
        AdminTransactionResponse.from_operation(operation) for operation in operations[offset:]
    ]


# One file's worth. A real system would generate bigger exports in the
# background; this is what a person opens in a spreadsheet.
_EXPORT_ROWS = 5000


# Declared with the rest of /transactions; there is no /transactions/{id}
# here for it to collide with.
@router.get(
    "/transactions/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "The operations as a CSV file."}},
)
async def export_all_transactions(
    type: TransactionType | None = Query(default=None),
    status: str | None = Query(default=None, max_length=32),
    user_id: UUID | None = Query(default=None),
    _: AuthenticatedUser = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """What `GET /api/v1/admin/transactions` lists under the same
    filters, as a CSV file (newest first, up to 5,000 rows), amounts as
    decimal strings. SUPPORT and ADMIN."""
    operations = await _operations(
        session, type=type, status=status, user_id=user_id, count=_EXPORT_ROWS
    )
    body = receipts.render_admin_csv(
        [AdminTransactionResponse.from_operation(operation) for operation in operations]
    )
    filename = f"fincore-transactions-{datetime.now(UTC):%Y-%m-%d}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


class DayStats(BaseModel):
    # A calendar day in UTC.
    date: date
    # Operations created that day.
    transfers: int
    payments: int
    exchanges: int
    # Transfers and payments of that day that ended FAILED or EXPIRED.
    failed: int
    # What the transfers and payments that went through moved.
    volume_minor: int


class CurrencyDayStats(BaseModel):
    currency: str
    # One entry per day, oldest first, zeros included.
    days: list[DayStats]


class PlatformStatsResponse(BaseModel):
    generated_at: datetime
    # Operations in the fraud review queue right now.
    awaiting_review: int
    # Only currencies with any operation in the period.
    currencies: list[CurrencyDayStats]


@router.get("/stats", response_model=PlatformStatsResponse)
async def get_platform_stats(
    days: int = Query(default=14, ge=1, le=90),
    _: AuthenticatedUser = Depends(_staff),
    session: AsyncSession = Depends(get_db),
) -> PlatformStatsResponse:
    """Per currency and per day (UTC) over the last `days` days: how
    many transfers, payments and exchanges were started, how many
    transfers and payments failed, and how much those that went through
    moved. SUPPORT and ADMIN."""
    stats = await admin_stats.platform_stats(session, days=days)
    return PlatformStatsResponse(
        generated_at=datetime.now(UTC),
        awaiting_review=stats.awaiting_review,
        currencies=[
            CurrencyDayStats(
                currency=currency,
                days=[
                    DayStats(
                        date=entry.day,
                        transfers=entry.transfers,
                        payments=entry.payments,
                        exchanges=entry.exchanges,
                        failed=entry.failed,
                        volume_minor=entry.volume_minor,
                    )
                    for entry in per_day
                ],
            )
            for currency, per_day in sorted(stats.by_currency.items())
        ],
    )
