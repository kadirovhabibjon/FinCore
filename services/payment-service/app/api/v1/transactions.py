from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import AuthenticatedUser, get_authenticated_user
from app.api.v1.schemas import TransactionResponse
from app.core.exceptions import TransactionNotFoundError
from app.db.session import get_db
from app.domain.transfer import TransferStatus
from app.repositories.exchange_repository import ExchangeRepository
from app.repositories.payment_repository import PaymentRepository
from app.repositories.transfer_repository import TransferRepository
from app.services import receipts

router = APIRouter(prefix="/api/v1/transactions", tags=["transactions"])


@router.get("", response_model=list[TransactionResponse])
async def list_transactions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> list[TransactionResponse]:
    """The caller's own business-operation history (spec Section 20),
    newest first across Transfer, Payment and Exchange: everything they
    started (`direction: OUT`) and every transfer that reached them
    (`direction: IN`). A merchant's received payments are on the
    merchant's own endpoints, not here.

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

    exchanges = await ExchangeRepository(session).list_for_user(
        user.user_id, limit=fetch_count, offset=0
    )

    combined = [TransactionResponse.from_exchange(exchange) for exchange in exchanges] + [
        TransactionResponse.from_transfer(transfer, viewer_user_id=user.user_id)
        for transfer in transfers
    ] + [
        TransactionResponse.from_payment(payment) for payment in payments
    ]
    combined.sort(key=lambda item: item.created_at, reverse=True)
    return combined[offset : offset + limit]


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
    user: AuthenticatedUser = Depends(get_authenticated_user),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """The caller's history as a CSV file for a spreadsheet: the same
    operations `GET /api/v1/transactions` lists (newest first, up to
    5,000), one per row, amounts as decimal strings."""
    transfers = await TransferRepository(session).list_for_user(
        user.user_id, limit=_STATEMENT_ROWS, offset=0
    )
    payments = await PaymentRepository(session).list_for_user(
        user.user_id, limit=_STATEMENT_ROWS, offset=0
    )
    exchanges = await ExchangeRepository(session).list_for_user(
        user.user_id, limit=_STATEMENT_ROWS, offset=0
    )
    listed = (
        [TransactionResponse.from_exchange(exchange) for exchange in exchanges]
        + [
            TransactionResponse.from_transfer(transfer, viewer_user_id=user.user_id)
            for transfer in transfers
        ]
        + [TransactionResponse.from_payment(payment) for payment in payments]
    )
    listed.sort(key=lambda item: item.created_at, reverse=True)
    merchants = {payment.id: payment.merchant_name for payment in payments}
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
            for item in listed[:_STATEMENT_ROWS]
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
