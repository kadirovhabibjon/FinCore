"""Receipts and statements a customer can keep: one operation as a PDF,
and their whole history as a CSV file.

Both are views of what the history endpoints already show that
customer: a receipt never says more than they can see in the app.
"""

import csv
import io
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from fincore_common import minor_to_decimal
from fpdf import FPDF
from fpdf.enums import XPos, YPos

from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.payment import Payment
from app.domain.transfer import Transfer
from app.services.exchanges import rate_text

_FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"
_FAMILY = "DejaVu"


def money(amount_minor: int, currency: str) -> str:
    """ "1,234.56 UZS" """
    return f"{minor_to_decimal(amount_minor, currency):,} {currency}"


def _when(moment: datetime | None) -> str:
    if moment is None:
        return "-"
    return moment.astimezone(UTC).strftime("%d %b %Y, %H:%M:%S UTC")


@dataclass(frozen=True)
class Receipt:
    """What is printed, as plain data: the PDF is only its layout."""

    title: str
    reference: str
    status: str
    # The headline amount, e.g. "250.00 UZS" (or both sides of an exchange).
    amount: str
    rows: list[tuple[str, str]] = field(default_factory=list)


def _card(number: str | None) -> str | None:
    return " ".join(number[i : i + 4] for i in range(0, len(number), 4)) if number else None


def transfer_receipt(transfer: Transfer, *, viewer_user_id: UUID) -> Receipt:
    incoming = transfer.initiator_user_id != viewer_user_id
    rows: list[tuple[str, str | None]]
    if incoming:
        rows = [("From", transfer.sender_name), ("To", "You")]
    else:
        rows = [
            ("From", "You"),
            ("To", transfer.recipient_name),
            ("To card", _card(transfer.recipient_card_number)),
            # Why it failed is the sender's to know.
            ("Reason", transfer.failure_reason),
        ]
    rows += [
        ("Note", transfer.description),
        ("Created", _when(transfer.created_at)),
        ("Completed", _when(transfer.completed_at) if transfer.completed_at else None),
        ("Transaction id", str(transfer.id)),
    ]
    return Receipt(
        title="Money received" if incoming else "Transfer",
        reference=transfer.reference,
        status=transfer.status.value,
        amount=money(transfer.amount_minor, transfer.currency),
        rows=[(label, value) for label, value in rows if value],
    )


def payment_receipt(payment: Payment) -> Receipt:
    rows: list[tuple[str, str | None]] = [
        ("Paid to", payment.merchant_name),
        ("Merchant id", str(payment.merchant_id)),
        (
            "Refunded",
            money(payment.refunded_amount_minor, payment.currency)
            if payment.refunded_amount_minor
            else None,
        ),
        ("Reason", payment.failure_reason),
        ("Note", payment.description),
        ("Created", _when(payment.created_at)),
        ("Completed", _when(payment.completed_at) if payment.completed_at else None),
        ("Transaction id", str(payment.id)),
    ]
    return Receipt(
        title="Payment",
        reference=payment.reference,
        status=payment.status.value,
        amount=money(payment.amount_minor, payment.currency),
        rows=[(label, value) for label, value in rows if value],
    )


def exchange_receipt(exchange: Exchange) -> Receipt:
    sold = money(exchange.source_amount_minor, exchange.source_currency)
    bought = money(exchange.destination_amount_minor, exchange.destination_currency)
    finished = exchange.status in (ExchangeStatus.COMPLETED, ExchangeStatus.FAILED)
    rows: list[tuple[str, str | None]] = [
        ("Sold", sold),
        ("Bought", bought),
        (
            "Rate",
            f"1 {exchange.source_currency} = {rate_text(exchange.rate)} "
            f"{exchange.destination_currency}",
        ),
        ("Fee", "None"),
        ("Reason", exchange.failure_reason),
        ("Created", _when(exchange.created_at)),
        ("Completed", _when(exchange.completed_at) if exchange.completed_at else None),
        ("Transaction id", str(exchange.id)),
    ]
    return Receipt(
        title="Currency exchange",
        reference=exchange.reference,
        # The saga's steps are one thing on paper: not finished yet.
        status=exchange.status.value if finished else "PROCESSING",
        amount=f"{sold} → {bought}",
        rows=[(label, value) for label, value in rows if value],
    )


_STATUS_NOTES = {
    "COMPLETED": "The money has moved.",
    "SUCCESS": "The payment went through.",
    "FAILED": "This did not go through. No money was taken.",
    "EXPIRED": "This expired before it was approved. No money was taken.",
    "CANCELLED": "This was cancelled. No money was taken.",
    "REFUNDED": "This payment was refunded in full.",
    "PARTIALLY_REFUNDED": "Part of this payment was refunded.",
}
_NOT_FINAL = "This is not finished yet: it is being processed or waiting for a review."


def render_pdf(receipt: Receipt, *, generated_at: datetime | None = None) -> bytes:
    """One A5 page. The fonts are bundled, so names and notes in Uzbek
    or Russian print as written rather than as question marks."""
    pdf = FPDF(format=(148, 210))  # A5, in millimetres
    pdf.set_creator("FinCore")
    pdf.set_title(f"{receipt.title} {receipt.reference}")
    pdf.add_font(_FAMILY, "", str(_FONTS / "DejaVuSans.ttf"))
    pdf.add_font(_FAMILY, "B", str(_FONTS / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_margins(14, 14, 14)
    pdf.add_page()
    width = pdf.epw

    pdf.set_font(_FAMILY, "B", 16)
    pdf.cell(width, 9, "FinCore", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(_FAMILY, "", 11)
    pdf.set_text_color(90, 100, 120)
    pdf.cell(width, 6, f"{receipt.title} receipt", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(4)

    pdf.set_text_color(20, 28, 45)
    pdf.set_font(_FAMILY, "B", 18)
    pdf.multi_cell(width, 9, receipt.amount, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(_FAMILY, "", 10)
    pdf.set_text_color(90, 100, 120)
    pdf.cell(
        width, 6, f"{receipt.reference} · {receipt.status}", new_x=XPos.LMARGIN, new_y=YPos.NEXT
    )
    pdf.ln(2)
    pdf.set_text_color(20, 28, 45)
    pdf.multi_cell(
        width,
        5.5,
        _STATUS_NOTES.get(receipt.status, _NOT_FINAL),
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    pdf.ln(3)
    pdf.set_draw_color(200, 206, 218)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + width, pdf.get_y())
    pdf.ln(3)

    label_width = 34
    for label, value in receipt.rows:
        top = pdf.get_y()
        pdf.set_font(_FAMILY, "", 9)
        pdf.set_text_color(90, 100, 120)
        pdf.cell(label_width, 6, label)
        pdf.set_xy(pdf.l_margin + label_width, top)
        pdf.set_text_color(20, 28, 45)
        pdf.set_font(_FAMILY, "", 10)
        pdf.multi_cell(width - label_width, 6, value, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    pdf.ln(4)
    pdf.set_font(_FAMILY, "", 8)
    pdf.set_text_color(120, 128, 145)
    printed = (generated_at or datetime.now(UTC)).astimezone(UTC)
    pdf.multi_cell(
        width,
        4.5,
        f"Generated {printed.strftime('%d %b %Y, %H:%M UTC')} from the account holder\u2019s "
        "own FinCore history. FinCore is a demonstration system: this is not a document "
        "of a licensed bank.",
        new_x=XPos.LMARGIN,
        new_y=YPos.NEXT,
    )
    return bytes(pdf.output())


# --- CSV statement ---------------------------------------------------------

CSV_COLUMNS = [
    "date_utc",
    "type",
    "direction",
    "reference",
    "status",
    "amount",
    "currency",
    "received_amount",
    "received_currency",
    "counterparty",
    "note",
]

# A cell starting with one of these is run as a formula by spreadsheet
# programs. Names and notes are typed by people - other people.
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe(text: str | None) -> str:
    value = text or ""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


@dataclass(frozen=True)
class StatementRow:
    created_at: datetime
    type: str
    direction: str
    reference: str
    status: str
    amount_minor: int
    currency: str
    received_amount_minor: int | None = None
    received_currency: str | None = None
    counterparty: str | None = None
    note: str | None = None


def render_csv(rows: list[StatementRow]) -> bytes:
    """UTF-8 with a byte-order mark, which is what makes Excel read
    names in Uzbek and Russian correctly. Amounts are decimal strings
    built from the integer minor units, never floats."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(
            [
                row.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                row.type,
                row.direction,
                row.reference,
                row.status,
                str(minor_to_decimal(row.amount_minor, row.currency)),
                row.currency,
                str(minor_to_decimal(row.received_amount_minor, row.received_currency))
                if row.received_amount_minor is not None and row.received_currency
                else "",
                row.received_currency or "",
                _safe(row.counterparty),
                _safe(row.note),
            ]
        )
    return out.getvalue().encode("utf-8-sig")


def render_admin_csv(operations: list[Any]) -> bytes:
    """Operations as the admin console lists them
    (`AdminTransactionResponse`), one per row. Ids are written whole:
    this file is for staff, who look things up by them."""
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(
        [
            "Date (UTC)",
            "Type",
            "Reference",
            "Status",
            "User id",
            "Amount",
            "Currency",
            "Received amount",
            "Received currency",
            "Source wallet id",
            "Counterparty id",
            "Counterparty name",
            "Failure reason",
            "Fraud decision",
            "Note",
        ]
    )
    for item in operations:
        received = (
            str(minor_to_decimal(item.received_amount_minor, item.received_currency))
            if item.received_amount_minor is not None and item.received_currency
            else ""
        )
        writer.writerow(
            [
                item.created_at.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S"),
                item.type.value,
                item.reference,
                item.status,
                str(item.initiator_user_id),
                str(minor_to_decimal(item.amount_minor, item.currency)),
                item.currency,
                received,
                item.received_currency or "",
                str(item.source_wallet_id),
                str(item.counterparty_id),
                _safe(item.counterparty_name),
                _safe(item.failure_reason),
                item.fraud_decision.value if item.fraud_decision else "",
                _safe(item.description),
            ]
        )
    return out.getvalue().encode("utf-8-sig")
