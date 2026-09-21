import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import fraud, ledger

pytestmark = pytest.mark.usefixtures("migrated_database")

_SOURCE_WALLET = uuid.uuid4()
_DEST_WALLET = uuid.uuid4()


def _ledger_app() -> FastAPI:
    fake = FastAPI()

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _get_wallet(wallet_id: str) -> JSONResponse:
        return JSONResponse(
            {
                "id": wallet_id,
                "currency": "UZS",
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "balance_minor": 0,
                "held_minor": 0,
            }
        )

    @fake.post("/internal/v1/postings")
    async def _post_posting(request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": str(uuid.uuid4()),
                "source_service": payload["source_service"],
                "source_id": payload["source_id"],
                "type": payload["type"],
                "currency": payload["currency"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            status_code=201,
        )

    @fake.post("/internal/v1/holds")
    async def _post_hold(request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": str(uuid.uuid4()),
                "account_id": payload["account_id"],
                "amount_minor": payload["amount_minor"],
                "currency": payload["currency"],
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-01-01T00:15:00Z",
                "resolved_at": None,
            },
            status_code=201,
        )

    @fake.post("/internal/v1/holds/{hold_id}/capture")
    async def _post_capture(hold_id: str, request: Request) -> JSONResponse:
        payload = await request.json()
        return JSONResponse(
            {
                "id": str(uuid.uuid4()),
                "source_service": payload["source_service"],
                "source_id": payload["source_id"],
                "type": "PAYMENT",
                "currency": "UZS",
                "created_at": "2026-01-01T00:00:00Z",
            },
            status_code=201,
        )

    return fake


def _wire_ledger(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_ledger_app()),
        ),
    )


def _wire_fraud(monkeypatch: pytest.MonkeyPatch, decision: str) -> None:
    fake = FastAPI()

    @fake.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": decision, "score": 10})

    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=httpx.ASGITransport(app=fake),
        ),
    )


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_transfer(client: AsyncClient, token: str, *, amount: str = "10.00") -> str:
    response = await client.post(
        "/api/v1/transfers",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "destination_wallet_id": str(_DEST_WALLET),
            "amount": amount,
            "currency": "UZS",
        },
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def _create_payment(client: AsyncClient, token: str, *, amount: str = "10.00") -> str:
    merchant_response = await client.post(
        "/api/v1/merchants",
        json={"name": "Test Shop"},
        headers={"Authorization": f"Bearer {token}"},
    )
    merchant_id = merchant_response.json()["id"]

    response = await client.post(
        "/api/v1/payments",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "merchant_id": merchant_id,
            "amount": amount,
            "currency": "UZS",
        },
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    return response.json()["id"]


async def test_listing_transactions_merges_transfers_and_payments_newest_first(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        transfer_id = await _create_transfer(client, token)
        payment_id = await _create_payment(client, token)

        response = await client.get(
            "/api/v1/transactions", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    ids = [item["id"] for item in body]
    assert set(ids) == {transfer_id, payment_id}
    # The payment was created after the transfer, so it sorts first.
    assert ids[0] == payment_id
    types = {item["id"]: item["type"] for item in body}
    assert types[transfer_id] == "TRANSFER"
    assert types[payment_id] == "PAYMENT"


async def test_getting_a_single_payment_transaction_by_id(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        payment_id = await _create_payment(client, token)

        response = await client.get(
            f"/api/v1/transactions/{payment_id}", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == payment_id
    assert body["type"] == "PAYMENT"
    assert body["status"] == "SUCCESS"


async def test_listing_transactions_returns_the_users_own_transfers_newest_first(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        first_id = await _create_transfer(client, token, amount="10.00")
        second_id = await _create_transfer(client, token, amount="20.00")

        response = await client.get(
            "/api/v1/transactions", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert [item["id"] for item in body] == [second_id, first_id]
    assert body[0]["type"] == "TRANSFER"
    assert body[0]["status"] == "COMPLETED"


async def test_listing_transactions_does_not_include_another_users_transfers(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    _wire_fraud(monkeypatch, "ALLOW")
    owner_token = issue_access_token(uuid.uuid4())
    other_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        await _create_transfer(client, owner_token)

        response = await client.get(
            "/api/v1/transactions", headers={"Authorization": f"Bearer {other_token}"}
        )

    assert response.status_code == 200
    assert response.json() == []


async def test_getting_a_single_transaction_by_id(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        transfer_id = await _create_transfer(client, token)

        response = await client.get(
            f"/api/v1/transactions/{transfer_id}", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == transfer_id
    assert body["type"] == "TRANSFER"


async def test_getting_someone_elses_transaction_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    _wire_fraud(monkeypatch, "ALLOW")
    owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        transfer_id = await _create_transfer(client, owner_token)

        response = await client.get(
            f"/api/v1/transactions/{transfer_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404


async def test_getting_a_nonexistent_transaction_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch)
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.get(
            f"/api/v1/transactions/{uuid.uuid4()}", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 404
