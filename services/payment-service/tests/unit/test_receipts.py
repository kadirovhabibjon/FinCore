"""Receipts and statements: what is printed, and that it survives
names and notes in any alphabet and anything a stranger typed."""

import csv
import io
import uuid
from datetime import UTC, datetime
from decimal import Decimal

from pypdf import PdfReader

from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.services import receipts
from app.services.receipts import StatementRow

_WHEN = datetime(2026, 10, 6, 9, 30, 15, tzinfo=UTC)
_SENDER, _RECIPIENT = uuid.uuid4(), uuid.uuid4()


def _transfer(**overrides: object) -> Transfer:
    values: dict = {
        "id": uuid.uuid4(),
        "reference": "TRF-RECEIPT01",
        "initiator_user_id": _SENDER,
        "recipient_user_id": _RECIPIENT,
        "source_wallet_id": uuid.uuid4(),
        "destination_wallet_id": uuid.uuid4(),
        "amount_minor": 1_250_000_00,
        "currency": "UZS",
        "status": TransferStatus.COMPLETED,
        "description": "Tushlik uchun",
        "sender_name": "Aziza K.",
        "recipient_name": "Бобур Т.",
        "recipient_card_number": "9955123456789011",
        "created_at": _WHEN,
        "completed_at": _WHEN,
    }
    values.update(overrides)
    return Transfer(**values)


def _text(pdf: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) == 1
    return " ".join(reader.pages[0].extract_text().split())


def test_the_senders_receipt_says_who_how_much_and_where_it_went() -> None:
    receipt = receipts.transfer_receipt(_transfer(), viewer_user_id=_SENDER)

    assert receipt.title == "Transfer"
    assert receipt.amount == "1,250,000.00 UZS"
    assert dict(receipt.rows)["To"] == "Бобур Т."
    assert dict(receipt.rows)["To card"] == "9955 1234 5678 9011"
    assert dict(receipt.rows)["Created"] == "06 Oct 2026, 09:30:15 UTC"


def test_the_recipients_receipt_shows_nothing_of_the_senders_side() -> None:
    transfer = _transfer(failure_reason="should never be shown")
    receipt = receipts.transfer_receipt(transfer, viewer_user_id=_RECIPIENT)

    assert receipt.title == "Money received"
    labels = [label for label, _ in receipt.rows]
    assert dict(receipt.rows)["From"] == "Aziza K." and dict(receipt.rows)["To"] == "You"
    assert "To card" not in labels and "Reason" not in labels


def test_the_pdf_prints_uzbek_and_cyrillic_as_written() -> None:
    pdf = receipts.render_pdf(
        receipts.transfer_receipt(_transfer(), viewer_user_id=_SENDER), generated_at=_WHEN
    )

    assert pdf.startswith(b"%PDF-") and pdf.rstrip().endswith(b"%%EOF")
    text = _text(pdf)
    for expected in (
        "FinCore",
        "Transfer receipt",
        "1,250,000.00 UZS",
        "TRF-RECEIPT01",
        "COMPLETED",
        "The money has moved.",
        "Бобур Т.",
        "Tushlik uchun",
        "9955 1234 5678 9011",
        "not a document of a licensed bank",
    ):
        assert expected in text, expected


def test_a_failed_or_unfinished_operation_is_never_printed_as_done() -> None:
    failed = receipts.transfer_receipt(
        _transfer(
            status=TransferStatus.FAILED, failure_reason="Insufficient Funds", completed_at=None
        ),
        viewer_user_id=_SENDER,
    )
    pending = receipts.transfer_receipt(
        _transfer(status=TransferStatus.PENDING, completed_at=None), viewer_user_id=_SENDER
    )

    failed_text = _text(receipts.render_pdf(failed))
    pending_text = _text(receipts.render_pdf(pending))

    assert "No money was taken" in failed_text and "Insufficient Funds" in failed_text
    assert "The money has moved" not in failed_text
    assert "not finished yet" in pending_text and "The money has moved" not in pending_text


def test_payment_and_exchange_receipts() -> None:
    payment = Payment(
        id=uuid.uuid4(),
        reference="PAY-RECEIPT01",
        initiator_user_id=_SENDER,
        source_wallet_id=uuid.uuid4(),
        merchant_id=uuid.uuid4(),
        merchant_name='Choyxona "Navro\'z"',
        amount_minor=45_000_00,
        refunded_amount_minor=10_000_00,
        currency="UZS",
        status=PaymentStatus.PARTIALLY_REFUNDED,
        created_at=_WHEN,
        completed_at=_WHEN,
    )
    exchange = Exchange(
        id=uuid.uuid4(),
        reference="EXC-RECEIPT01",
        initiator_user_id=_SENDER,
        source_wallet_id=uuid.uuid4(),
        destination_wallet_id=uuid.uuid4(),
        source_position_account_id=uuid.uuid4(),
        destination_position_account_id=uuid.uuid4(),
        source_amount_minor=1_200_000_00,
        source_currency="UZS",
        destination_amount_minor=100_00,
        destination_currency="USD",
        rate=Decimal("1") / Decimal("12000"),
        status=ExchangeStatus.DEBITED,
        created_at=_WHEN,
    )

    paid = receipts.payment_receipt(payment)
    swapped = receipts.exchange_receipt(exchange)

    assert dict(paid.rows)["Paid to"] == 'Choyxona "Navro\'z"'
    assert dict(paid.rows)["Refunded"] == "10,000.00 UZS"
    assert "Part of this payment was refunded" in _text(receipts.render_pdf(paid))
    assert swapped.amount == "1,200,000.00 UZS → 100.00 USD"
    assert swapped.status == "PROCESSING"  # mid-saga is "not finished", not a saga step
    assert dict(swapped.rows)["Rate"] == "1 UZS = 0.000083333333333 USD"
    assert "not finished yet" in _text(receipts.render_pdf(swapped))


def test_a_very_long_note_wraps_instead_of_running_off_the_page() -> None:
    receipt = receipts.transfer_receipt(_transfer(description="so'z " * 50), viewer_user_id=_SENDER)

    assert _text(receipts.render_pdf(receipt)).count("so'z") == 50


def _rows(data: bytes) -> list[dict[str, str]]:
    assert data.startswith(b"\xef\xbb\xbf")  # the BOM Excel needs for non-Latin text
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def test_the_statement_has_one_row_per_operation_with_exact_amounts() -> None:
    rows = _rows(
        receipts.render_csv(
            [
                StatementRow(
                    _WHEN,
                    "TRANSFER",
                    "IN",
                    "TRF-1",
                    "COMPLETED",
                    1_250_000_05,
                    "UZS",
                    counterparty="Бобур Т.",
                    note='Rahmat, "do\'stim"',
                ),
                StatementRow(
                    _WHEN,
                    "EXCHANGE",
                    "SELF",
                    "EXC-1",
                    "COMPLETED",
                    1_200_000_00,
                    "UZS",
                    received_amount_minor=100_00,
                    received_currency="USD",
                ),
            ]
        )
    )

    assert list(rows[0]) == receipts.CSV_COLUMNS
    assert rows[0]["date_utc"] == "2026-10-06 09:30:15"
    assert rows[0]["amount"] == "1250000.05" and rows[0]["currency"] == "UZS"
    assert rows[0]["counterparty"] == "Бобур Т."
    assert rows[0]["note"] == 'Rahmat, "do\'stim"'
    assert (rows[1]["received_amount"], rows[1]["received_currency"]) == ("100.00", "USD")
    assert rows[0]["received_amount"] == ""


def test_text_someone_else_typed_cannot_become_a_spreadsheet_formula() -> None:
    hostile = ['=HYPERLINK("http://evil.example","click")', "+1+1", "-2", "@SUM(A1)", "\tx"]
    rows = _rows(
        receipts.render_csv(
            [
                StatementRow(
                    _WHEN,
                    "TRANSFER",
                    "IN",
                    "TRF-1",
                    "COMPLETED",
                    100,
                    "UZS",
                    counterparty=text,
                    note=text,
                )
                for text in hostile
            ]
        )
    )

    for row, text in zip(rows, hostile, strict=True):
        assert row["note"] == f"'{text}" and row["counterparty"] == f"'{text}"
    # Numbers stay numbers: only free text is touched.
    assert rows[0]["amount"] == "1.00"
