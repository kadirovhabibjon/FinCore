from datetime import UTC, date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import TransactionDirection, TransactionResponse, TransactionType
from app.core.exceptions import TransactionNotFoundError
from app.db.session import get_db
from app.domain.transfer import TransferStatus
from app.repositories.exchange_repository import ExchangeRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.transfer_repository import TransferRepository
from app.services import history, receipts, statistics
from app.services.history import HistoryFilter

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


def history_filter(
    type: TransactionType | None = Query(default=None),
    direction: TransactionDirection | None = Query(default=None),
    q: str | None = Query(default=None, max_length=64),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
) -> HistoryFilter:
    """The query parameters that narrow a history listing: the kind of
    operation, its direction (IN received, OUT sent or paid, SELF an
    exchange), words to find in the reference, the note or the other
    side's name, and a range of calendar days (UTC, both included)."""
    return HistoryFilter(type=type, direction=direction, q=q, date_from=date_from, date_to=date_to)


async def _history(
    session: AsyncSession, user_id: UUID, wanted: HistoryFilter, *, count: int
) -> tuple[list[TransactionResponse], dict[UUID, str | None]]:
    """The caller's newest `count` operations matching the filter,
    newest first, and the merchants' names of the payments among them.

    Merged and sorted in Python rather than a single SQL query, since
    each operation type has its own table (spec Section 7.1) - a
    reasonable v1 approach at this scale; a UNION query would be the
    next step if this list ever pages over a serious volume of rows.
    """
    listed: list[TransactionResponse] = []
    merchants: dict[UUID, str | None] = {}

    where = history.for_exchanges(wanted)
    if where is not None:
        exchanges = await ExchangeRepository(session).list_for_user(
            user_id, limit=count, offset=0, where=where
        )
        listed += [TransactionResponse.from_exchange(exchange) for exchange in exchanges]
    where = history.for_transfers(wanted, user_id)
    if where is not None:
        transfers = await TransferRepository(session).list_for_user(
            user_id, limit=count, offset=0, where=where
        )
        listed += [
            TransactionResponse.from_transfer(transfer, viewer_user_id=user_id)
            for transfer in transfers
        ]
    where = history.for_payments(wanted)
    if where is not None:
        payments = await PaymentRepository(session).list_for_user(
            user_id, limit=count, offset=0, where=where
        )
        listed += [TransactionResponse.from_payment(payment) for payment in payments]
        merchants = {payment.id: payment.merchant_name for payment in payments}

    listed.sort(key=lambda item: item.created_at, reverse=True)
    return listed[:count], merchants


@router.get("", response_model=list[TransactionResponse])
async def list_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    wanted: HistoryFilter = Depends(history_filter),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[TransactionResponse]:
    """The caller's own business-operation history (spec Section 20),
    newest first across Transfer, Payment and Exchange: everything they
    started (`direction: OUT`, or `SELF` for an exchange) and every
    transfer that reached them (`direction: IN`). A merchant's received
    payments are on the merchant's own endpoints, not here. Optionally
    narrowed - see the query parameters.
    """
    listed, _ = await _history(session, user.user_id, wanted, count=limit + offset)
    return listed[offset:]


class MonthStats(BaseModel):
    # Calendar month in UTC, "YYYY-MM".
    month: str
    in_minor: int
    out_minor: int


class CurrencyStats(BaseModel):
    currency: str
    total_in_minor: int
    total_out_minor: int
    # One entry per month of the period, oldest first, zeros included.
    months: list[MonthStats]


class StatsResponse(BaseModel):
    # The months covered, oldest first.
    months: list[str]
    # Only currencies with any movement in the period.
    currencies: list[CurrencyStats]


@router.get("/stats", response_model=StatsResponse)
async def get_statistics(
    months: int = Query(default=6, ge=1, le=24),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> StatsResponse:
    """Money in and money out per calendar month (UTC), per currency.
    Out: completed transfers the caller sent and captured payments, net
    of refunds. In: transfers that reached the caller. Exchanges are not
    counted (the caller's own money changing currency), nor are
    top-ups or a merchant's received payments."""
    totals = await statistics.monthly_totals(session, user.user_id, months=months)
    return StatsResponse(
        months=statistics.month_keys(datetime.now(UTC), months),
        currencies=[
            CurrencyStats(
                currency=currency,
                total_in_minor=sum(entry.in_minor for entry in entries),
                total_out_minor=sum(entry.out_minor for entry in entries),
                months=[
                    MonthStats(month=e.month, in_minor=e.in_minor, out_minor=e.out_minor)
                    for e in entries
                ],
            )
            for currency, entries in totals.items()
        ],
    )


class CategorySpending(BaseModel):
    # MOBILE, INTERNET, UTILITIES, TV (payments to service providers),
    # SHOPS (payments to merchants), TRANSFERS (money sent to people),
    # or OTHER.
    category: str
    amount_minor: int
    # How many operations that is.
    count: int


class CurrencySpending(BaseModel):
    currency: str
    total_minor: int
    # Largest first.
    categories: list[CategorySpending]


class SpendingResponse(BaseModel):
    # The calendar months covered, oldest first, "YYYY-MM".
    months: list[str]
    # Only currencies in which something was spent.
    currencies: list[CurrencySpending]


@router.get("/stats/categories", response_model=SpendingResponse)
async def get_spending_by_category(
    months: int = Query(default=1, ge=1, le=24),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> SpendingResponse:
    """What the caller's money out went on over the last `months`
    calendar months (UTC), per currency, largest first: the same money
    `GET /api/v1/transactions/stats` reports as out, split by what it
    paid for."""
    spending = await statistics.spending_by_category(session, user.user_id, months=months)
    return SpendingResponse(
        months=statistics.month_keys(datetime.now(UTC), months),
        currencies=[
            CurrencySpending(
                currency=currency,
                total_minor=sum(total.amount_minor for total in totals),
                categories=[
                    CategorySpending(
                        category=total.category,
                        amount_minor=total.amount_minor,
                        count=total.count,
                    )
                    for total in totals
                ],
            )
            for currency, totals in spending.items()
        ],
    )


# How much history one statement holds. Enough for years of a person's
# use; a real system would page or generate it in the background.
_STATEMENT_ROWS = 5000


# Declared before /{transaction_id} so the literal path is matched first.
@router.get(
    "/export.csv",
    response_class=Response,
    responses={200: {"content": {"text/csv": {}}, "description": "The statement as a CSV file."}},
)
async def export_transactions(
    wanted: HistoryFilter = Depends(history_filter),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """The caller's history as a CSV file for a spreadsheet: the same
    operations `GET /api/v1/transactions` lists under the same filters
    (newest first, up to 5,000), one per row, amounts as decimal
    strings."""
    listed, merchants = await _history(session, user.user_id, wanted, count=_STATEMENT_ROWS)
    body = receipts.render_csv(
        [
            receipts.StatementRow(
                created_at=item.created_at,
                type=item.type.value,
                direction=item.direction.value,
                reference=item.reference,
                status=item.status,
                amount_minor=item.amount_minor,
                currency=item.currency,
                received_amount_minor=item.received_amount_minor,
                received_currency=item.received_currency,
                counterparty=item.counterparty_name or merchants.get(item.id),
                note=item.description,
            )
            for item in listed
        ]
    )
    filename = f"fincore-history-{datetime.now(UTC):%Y-%m-%d}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.get(
    "/{transaction_id}/receipt.pdf",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}, "description": "The receipt as a PDF."}},
)
async def download_receipt(
    transaction_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """A one-page PDF receipt for a transfer, payment or exchange the
    caller can see in their history: one they started, or a transfer
    that reached them. It says what the app shows that customer, and
    for an operation that is not finished or failed, says so."""
    receipt: receipts.Receipt | None = None
    transfer = await TransferRepository(session).get(transaction_id)
    if transfer is not None and (
        transfer.initiator_user_id == user.user_id
        or (
            transfer.recipient_user_id == user.user_id
            and transfer.status == TransferStatus.COMPLETED
        )
    ):
        receipt = receipts.transfer_receipt(transfer, viewer_user_id=user.user_id)
    if receipt is None:
        payment = await PaymentRepository(session).get(transaction_id)
        if payment is not None and payment.initiator_user_id == user.user_id:
            receipt = receipts.payment_receipt(payment)
    if receipt is None:
        exchange = await ExchangeRepository(session).get(transaction_id)
        if exchange is not None and exchange.initiator_user_id == user.user_id:
            receipt = receipts.exchange_receipt(exchange)
    if receipt is None:
        raise TransactionNotFoundError(str(transaction_id))

    return Response(
        content=receipts.render_pdf(receipt),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="fincore-{receipt.reference}.pdf"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/{transaction_id}", response_model=TransactionResponse)
async def get_transaction(
    transaction_id: UUID,
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> TransactionResponse:
    transfer = await TransferRepository(session).get(transaction_id)
    if transfer is not None and (
        transfer.initiator_user_id == user.user_id
        or (
            transfer.recipient_user_id == user.user_id
            and transfer.status == TransferStatus.COMPLETED
        )
    ):
        return TransactionResponse.from_transfer(transfer, viewer_user_id=user.user_id)

    payment = await PaymentRepository(session).get(transaction_id)
    if payment is not None and payment.initiator_user_id == user.user_id:
        return TransactionResponse.from_payment(payment)

    exchange = await ExchangeRepository(session).get(transaction_id)
    if exchange is not None and exchange.initiator_user_id == user.user_id:
        return TransactionResponse.from_exchange(exchange)

    raise TransactionNotFoundError(str(transaction_id))
