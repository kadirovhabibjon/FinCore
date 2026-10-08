"""The admin console beyond the review queue: exchanges among the
transactions, the CSV export, and the platform statistics."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import update

from app.db import session as db_session
from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.idempotency import IdempotencyKey
from app.domain.payment import Payment
from app.domain.transfer import Transfer
from tests.integration import test_admin_api as console
from tests.integration.test_admin_api import _LedgerCalls

pytestmark = pytest.mark.usefixtures("migrated_database")

ledger_calls = console.ledger_calls  # the fixture: a fake ledger wired in


async def _exchange(
    user_id: uuid.UUID,
    status: ExchangeStatus = ExchangeStatus.COMPLETED,
    *,
    failure_reason: str | None = None,
) -> Exchange:
    """An exchange as its saga would have left it, without running one."""
    async with db_session.async_session_factory() as session:
        key = IdempotencyKey(
            user_id=user_id,
            key=str(uuid.uuid4()),
            request_fingerprint="0" * 64,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        session.add(key)
        await session.flush()
        exchange = Exchange(
            initiator_user_id=user_id,
            source_wallet_id=uuid.uuid4(),
            destination_wallet_id=uuid.uuid4(),
            source_position_account_id=uuid.uuid4(),
            destination_position_account_id=uuid.uuid4(),
            source_amount_minor=10_000,
            source_currency="USD",
            destination_amount_minor=120_000_000,
            destination_currency="UZS",
            rate=Decimal("12000"),
            status=status,
            failure_reason=failure_reason,
            idempotency_key_id=key.id,
        )
        session.add(exchange)
        await session.commit()
        await session.refresh(exchange)
        return exchange


def _rows(response_text: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(response_text.lstrip("﻿"))))


async def test_exchanges_are_listed_among_everyones_transactions(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    console._wire_fraud(monkeypatch, "ALLOW")
    alice_id = uuid.uuid4()
    staff = console._auth(issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"]))

    async with console._client() as client:
        transfer = await console._post_transfer(client, issue_access_token(alice_id))
        done = await _exchange(alice_id)
        failed = await _exchange(uuid.uuid4(), ExchangeStatus.FAILED, failure_reason="Rate Changed")
        midway = await _exchange(uuid.uuid4(), ExchangeStatus.DEBITED)

        async def listed(**params: str) -> list[dict]:
            response = await client.get(
                "/api/v1/admin/transactions", params=params, headers=staff
            )
            assert response.status_code == 200, response.text
            return response.json()

        everything = await listed()
        exchanges = await listed(type="EXCHANGE")
        of_alice = await listed(user_id=str(alice_id))
        completed = await listed(status="COMPLETED")
        processing = await listed(status="PROCESSING")
        only_payments = await listed(type="PAYMENT")

    assert [item["id"] for item in everything] == [
        str(midway.id),
        str(failed.id),
        str(done.id),
        transfer["id"],
    ]
    assert [item["id"] for item in exchanges] == [str(midway.id), str(failed.id), str(done.id)]
    assert [item["id"] for item in of_alice] == [str(done.id), transfer["id"]]
    # COMPLETED is a state of transfers and of exchanges.
    assert [item["id"] for item in completed] == [str(done.id), transfer["id"]]
    # An exchange part-way through its saga is, to anyone looking, in progress.
    assert [item["id"] for item in processing] == [str(midway.id)]
    assert only_payments == []

    shown = exchanges[2]
    assert (shown["type"], shown["direction"], shown["status"]) == ("EXCHANGE", "SELF", "COMPLETED")
    assert (shown["amount_minor"], shown["currency"]) == (10_000, "USD")
    assert (shown["received_amount_minor"], shown["received_currency"]) == (120_000_000, "UZS")
    assert shown["initiator_user_id"] == str(alice_id)
    assert shown["counterparty_id"] == str(done.destination_wallet_id)
    assert shown["fraud_decision"] is None and shown["reviewed_by_user_id"] is None
    assert exchanges[1]["failure_reason"] == "Rate Changed"


async def test_the_listing_can_be_downloaded_as_csv_under_the_same_filters(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    console._wire_fraud(monkeypatch, "ALLOW")
    alice_id = uuid.uuid4()
    alice = issue_access_token(alice_id)
    staff = console._auth(issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"]))

    async with console._client() as client:
        transfer = await console._post_transfer(client, alice)
        payment = await console._post_payment(client, issue_access_token(uuid.uuid4()))
        exchange = await _exchange(alice_id)
        async with db_session.async_session_factory() as session:
            # What a spreadsheet would run as a formula if written as is.
            await session.execute(
                update(Transfer)
                .where(Transfer.id == uuid.UUID(transfer["id"]))
                .values(description="=HYPERLINK(1)")
            )
            await session.commit()

        everything = await client.get("/api/v1/admin/transactions/export.csv", headers=staff)
        of_alice = await client.get(
            "/api/v1/admin/transactions/export.csv",
            params={"user_id": str(alice_id), "type": "TRANSFER"},
            headers=staff,
        )
        as_customer = await client.get(
            "/api/v1/admin/transactions/export.csv", headers=console._auth(alice)
        )
        anonymous = await client.get("/api/v1/admin/transactions/export.csv")

    assert as_customer.status_code == 403 and anonymous.status_code == 401
    assert everything.status_code == 200
    assert everything.headers["content-type"] == "text/csv; charset=utf-8"
    assert everything.headers["content-disposition"].startswith(
        'attachment; filename="fincore-transactions-'
    )
    assert everything.content.startswith(b"\xef\xbb\xbf")  # Excel reads it as UTF-8

    rows = _rows(everything.text)
    assert [row["Reference"] for row in rows] == [
        exchange.reference,
        payment["reference"],
        transfer["reference"],
    ]
    assert rows[0] | {"Date (UTC)": ""} == {
        "Date (UTC)": "",
        "Type": "EXCHANGE",
        "Reference": exchange.reference,
        "Status": "COMPLETED",
        "User id": str(alice_id),
        "Amount": "100.00",
        "Currency": "USD",
        "Received amount": "1200000.00",
        "Received currency": "UZS",
        "Source wallet id": str(exchange.source_wallet_id),
        "Counterparty id": str(exchange.destination_wallet_id),
        "Counterparty name": "",
        "Failure reason": "",
        "Fraud decision": "",
        "Note": "",
    }
    assert (rows[2]["Amount"], rows[2]["Currency"], rows[2]["Fraud decision"]) == (
        "100.00",
        "UZS",
        "ALLOW",
    )
    # Defused: text, not a formula.
    assert rows[2]["Note"] == "'=HYPERLINK(1)"
    assert [row["Reference"] for row in _rows(of_alice.text)] == [transfer["reference"]]


async def test_platform_statistics_count_each_day_and_currency(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    console._wire_fraud(monkeypatch, "ALLOW")
    staff = console._auth(issue_access_token(uuid.uuid4(), ["USER", "ADMIN"]))
    customer = issue_access_token(uuid.uuid4())
    today = datetime.now(UTC).date()

    async with console._client() as client:
        old = await console._post_transfer(client, customer)  # moved to two days ago below
        await console._post_transfer(client, customer)
        failed = await console._post_transfer(client, customer)
        await console._post_payment(client, customer)
        too_old = await console._post_payment(client, customer)
        await _exchange(uuid.uuid4())
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Transfer)
                .where(Transfer.id == uuid.UUID(old["id"]))
                .values(created_at=datetime.now(UTC) - timedelta(days=2))
            )
            await session.execute(
                update(Transfer)
                .where(Transfer.id == uuid.UUID(failed["id"]))
                .values(status="FAILED")
            )
            await session.execute(
                update(Payment)
                .where(Payment.id == uuid.UUID(too_old["id"]))
                .values(created_at=datetime.now(UTC) - timedelta(days=30))
            )
            await session.commit()

        response = await client.get("/api/v1/admin/stats", params={"days": 3}, headers=staff)
        as_customer = await client.get("/api/v1/admin/stats", headers=console._auth(customer))
        too_many = await client.get("/api/v1/admin/stats", params={"days": 91}, headers=staff)

    assert as_customer.status_code == 403 and too_many.status_code == 422
    assert response.status_code == 200
    stats = response.json()
    assert stats["awaiting_review"] == 0
    by_currency = {entry["currency"]: entry["days"] for entry in stats["currencies"]}
    assert sorted(by_currency) == ["USD", "UZS"]

    uzs = by_currency["UZS"]
    assert [day["date"] for day in uzs] == [
        str(today - timedelta(days=2)),
        str(today - timedelta(days=1)),
        str(today),
    ]
    zero = {"transfers": 0, "payments": 0, "exchanges": 0, "failed": 0, "volume_minor": 0}
    assert uzs[0] == {"date": str(today - timedelta(days=2)), **zero, "transfers": 1,
                      "volume_minor": 10_000}
    assert uzs[1] == {"date": str(today - timedelta(days=1)), **zero}
    # Two transfers today (one failed: counted, but it moved nothing) and one payment.
    assert uzs[2] == {
        "date": str(today),
        "transfers": 2,
        "payments": 1,
        "exchanges": 0,
        "failed": 1,
        "volume_minor": 10_000 + 5_000,
    }
    # An exchange is counted in the currency sold, and moves no volume.
    assert by_currency["USD"][2] == {"date": str(today), **zero, "exchanges": 1}


async def test_platform_statistics_report_the_review_queue(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    console._wire_fraud(monkeypatch, "REVIEW")
    staff = console._auth(issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"]))
    customer = issue_access_token(uuid.uuid4())

    async with console._client() as client:
        await console._post_transfer(client, customer)
        await console._post_payment(client, customer)
        empty_period = await client.get("/api/v1/admin/stats", params={"days": 1}, headers=staff)

    stats = empty_period.json()
    assert stats["awaiting_review"] == 2
    # Waiting for a decision: started, neither moved nor failed.
    today = stats["currencies"][0]["days"][0]
    assert (today["transfers"], today["payments"], today["failed"], today["volume_minor"]) == (
        1,
        1,
        0,
        0,
    )
