"""A customer's own daily sending limit on a wallet (app/services/limits.py)."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select, update

from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.domain.transfer import Transfer
from tests.integration import test_payment_saga as payments
from tests.integration import test_transfer_saga as transfers

pytestmark = pytest.mark.usefixtures("migrated_database")

_DESTINATION = uuid.uuid4()


def _wire(monkeypatch: pytest.MonkeyPatch, *, wallet_found: bool = True) -> list[dict]:
    posting_calls: list[dict] = []
    transfers._wire_ledger(
        monkeypatch,
        transfers._ledger_app(posting_calls=posting_calls, wallet_found=wallet_found),
    )
    transfers._wire_fraud(monkeypatch, "ALLOW")
    return posting_calls


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _send(
    client: AsyncClient, token: str, wallet: uuid.UUID, amount: str, key: str | None = None
) -> dict:
    response = await client.post(
        "/api/v1/transfers",
        json={
            "source_wallet_id": str(wallet),
            "destination_wallet_id": str(_DESTINATION),
            "amount": amount,
            "currency": "UZS",
        },
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )
    return {"status_code": response.status_code, **response.json()}


async def test_a_wallet_has_no_limit_until_its_owner_sets_one(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        before = await client.get(f"/api/v1/limits/{wallet}", headers=_auth(token))
        sent = await _send(client, token, wallet, "5000000.00")
        after = await client.get(f"/api/v1/limits/{wallet}", headers=_auth(token))

    assert before.status_code == 200
    assert before.json() == {
        "wallet_id": str(wallet),
        "currency": "UZS",
        "daily_limit_minor": None,
        "spent_minor": 0,
        "remaining_minor": None,
        "window_hours": 24,
    }
    assert sent["status"] == "COMPLETED"
    assert after.json()["spent_minor"] == 500_000_000


async def test_the_limit_counts_what_was_sent_and_refuses_what_would_pass_it(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    posting_calls = _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        set_ = await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1000.00"}, headers=_auth(token)
        )
        first = await _send(client, token, wallet, "600.00")
        too_much = await _send(client, token, wallet, "400.01")
        exactly = await _send(client, token, wallet, "400.00")
        status = await client.get(f"/api/v1/limits/{wallet}", headers=_auth(token))

    assert set_.status_code == 200 and set_.json()["daily_limit_minor"] == 100_000
    assert first["status"] == "COMPLETED"
    assert too_much["status_code"] == 201
    assert too_much["status"] == "FAILED"
    assert too_much["failure_reason"] == "Daily Limit Exceeded"
    assert exactly["status"] == "COMPLETED"
    assert status.json()["spent_minor"] == 100_000
    assert status.json()["remaining_minor"] == 0
    assert len(posting_calls) == 2  # the failed one never reached the ledger


async def test_requests_racing_past_the_limit_cannot_all_succeed(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    """Each alone fits; together they don't. The decision is made with
    the wallet's lock held, in the transaction that records the
    transfer, so each sees the ones before it."""
    posting_calls = _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1000.00"}, headers=_auth(token)
        )
        results = await asyncio.gather(*(_send(client, token, wallet, "400.00") for _ in range(6)))
        status = await client.get(f"/api/v1/limits/{wallet}", headers=_auth(token))

    completed = [result for result in results if result.get("status") == "COMPLETED"]
    refused = [result for result in results if result not in completed]
    assert len(completed) == 2
    assert len(posting_calls) == 2
    assert status.json()["spent_minor"] == 80_000
    assert len(refused) == 4
    for result in refused:
        assert result["status"] == "FAILED"
        assert result["failure_reason"] == "Daily Limit Exceeded"

    async with db_session.async_session_factory() as session:
        failed = (
            await session.execute(
                select(Transfer).where(
                    Transfer.source_wallet_id == wallet, Transfer.status == "FAILED"
                )
            )
        ).scalars().all()
        events = (
            await session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.aggregate_id.in_([str(transfer.id) for transfer in failed])
                )
            )
        ).scalars().all()
    # Every transfer recorded as failed told the world so, exactly once.
    assert sorted(event.event_type for event in events) == ["transfer.failed"] * len(failed)


async def test_a_request_replays_its_first_answer_even_once_the_limit_is_used_up(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    posting_calls = _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()
    used_it_up, over = str(uuid.uuid4()), str(uuid.uuid4())

    async with await transfers._client() as client:
        await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1000.00"}, headers=_auth(token)
        )
        first = await _send(client, token, wallet, "1000.00", used_it_up)
        failed = await _send(client, token, wallet, "1.00", over)
        first_again = await _send(client, token, wallet, "1000.00", used_it_up)
        failed_again = await _send(client, token, wallet, "1.00", over)

    assert first["status"] == "COMPLETED" and failed["status"] == "FAILED"
    assert first_again == first
    assert failed_again == failed
    assert len(posting_calls) == 1


async def test_what_was_sent_more_than_a_day_ago_no_longer_counts(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1000.00"}, headers=_auth(token)
        )
        assert (await _send(client, token, wallet, "1000.00"))["status"] == "COMPLETED"
        assert (await _send(client, token, wallet, "1.00"))["status"] == "FAILED"

        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Transfer)
                .where(Transfer.source_wallet_id == wallet)
                .values(created_at=datetime.now(UTC) - timedelta(hours=24, minutes=1))
            )
            await session.commit()

        later = await _send(client, token, wallet, "1.00")

    assert later["status"] == "COMPLETED"


async def test_failed_operations_do_not_use_up_the_limit(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    transfers._wire_ledger(monkeypatch, transfers._ledger_app(posting_status=409))
    transfers._wire_fraud(monkeypatch, "ALLOW")
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1000.00"}, headers=_auth(token)
        )
        failed = await _send(client, token, wallet, "900.00")
        status = await client.get(f"/api/v1/limits/{wallet}", headers=_auth(token))

    assert failed["status"] == "FAILED"
    assert status.json()["spent_minor"] == 0


async def test_merchant_payments_count_towards_the_same_limit(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    payments._wire_ledger(monkeypatch, payments._ledger_app())
    payments._wire_fraud(monkeypatch, "ALLOW")
    user_id, wallet = uuid.uuid4(), uuid.uuid4()
    token = issue_access_token(user_id)
    merchant_id = await payments._create_active_merchant(uuid.uuid4())

    async def pay(client: AsyncClient, amount: str) -> dict:
        response = await client.post(
            "/api/v1/payments",
            json={
                "source_wallet_id": str(wallet),
                "merchant_id": str(merchant_id),
                "amount": amount,
                "currency": "UZS",
            },
            headers={**_auth(token), "Idempotency-Key": str(uuid.uuid4())},
        )
        return {"status_code": response.status_code, **response.json()}

    async with await payments._client() as client:
        await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1000.00"}, headers=_auth(token)
        )
        paid = await pay(client, "800.00")
        refused = await pay(client, "300.00")
        sent = await _send(client, token, wallet, "300.00")
        raced = await asyncio.gather(*(pay(client, "150.00") for _ in range(4)))

    assert paid["status"] == "SUCCESS"
    assert refused["status"] == "FAILED"
    assert refused["failure_reason"] == "Daily Limit Exceeded"
    assert sent["status"] == "FAILED"
    assert [result.get("status") for result in raced].count("SUCCESS") == 1


async def test_the_limit_can_be_changed_and_removed(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        url = f"/api/v1/limits/{wallet}"
        await client.put(url, json={"daily_limit": "100.00"}, headers=_auth(token))
        assert (await _send(client, token, wallet, "500.00"))["status"] == "FAILED"
        raised = await client.put(url, json={"daily_limit": "500.00"}, headers=_auth(token))
        assert (await _send(client, token, wallet, "500.00"))["status"] == "COMPLETED"
        removed = await client.put(url, json={"daily_limit": None}, headers=_auth(token))
        assert (await _send(client, token, wallet, "9000.00"))["status"] == "COMPLETED"
        again = await client.put(url, json={"daily_limit": None}, headers=_auth(token))

    assert raised.json()["daily_limit_minor"] == 50_000
    assert removed.json()["daily_limit_minor"] is None and removed.json()["remaining_minor"] is None
    assert again.status_code == 200


@pytest.mark.parametrize("bad", ["0", "-5", "abc", "1.234", ""])
async def test_a_limit_must_be_a_positive_amount(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, bad: str
) -> None:
    _wire(monkeypatch)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        response = await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": bad}, headers=_auth(token)
        )

    assert response.status_code == 422
    assert response.json()["title"] == "Invalid Amount"


async def test_limits_belong_to_the_wallets_owner(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    # ledger-service says the wallet is not the caller's.
    _wire(monkeypatch, wallet_found=False)
    token, wallet = issue_access_token(uuid.uuid4()), uuid.uuid4()

    async with await transfers._client() as client:
        read = await client.get(f"/api/v1/limits/{wallet}", headers=_auth(token))
        write = await client.put(
            f"/api/v1/limits/{wallet}", json={"daily_limit": "1.00"}, headers=_auth(token)
        )
        anonymous = await client.get(f"/api/v1/limits/{wallet}")

    assert read.status_code == write.status_code == 404
    assert read.json()["title"] == "Wallet Not Found"
    assert anonymous.status_code == 401
