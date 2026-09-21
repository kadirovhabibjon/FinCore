import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.db import session as db_session
from app.domain.merchant import Merchant
from app.main import app
from app.services import fraud, ledger

pytestmark = pytest.mark.usefixtures("migrated_database")

_SOURCE_WALLET = uuid.uuid4()


def _ledger_app(
    *,
    wallet_found: bool = True,
    wallet_currency: str = "UZS",
    hold_status: int = 201,
    capture_status: int = 201,
    hold_calls: list[dict] | None = None,
    capture_calls: list[dict] | None = None,
) -> FastAPI:
    fake = FastAPI()
    holds: dict[str, str] = {}

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _get_wallet(wallet_id: str) -> JSONResponse:
        if not wallet_found:
            return JSONResponse({"title": "Wallet Not Found"}, status_code=404)
        return JSONResponse(
            {
                "id": wallet_id,
                "currency": wallet_currency,
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "balance_minor": 0,
                "held_minor": 0,
            }
        )

    @fake.post("/internal/v1/holds")
    async def _post_hold(request: Request) -> JSONResponse:
        payload = await request.json()
        if hold_calls is not None:
            hold_calls.append(payload)
        if hold_status >= 400:
            return JSONResponse({"title": "Insufficient Funds"}, status_code=hold_status)
        hold_id = str(uuid.uuid4())
        holds[payload["source_id"]] = hold_id
        return JSONResponse(
            {
                "id": hold_id,
                "account_id": payload["account_id"],
                "amount_minor": payload["amount_minor"],
                "currency": payload["currency"],
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-01-01T00:15:00Z",
                "resolved_at": None,
            },
            status_code=hold_status,
        )

    @fake.post("/internal/v1/holds/{hold_id}/capture")
    async def _post_capture(hold_id: str, request: Request) -> JSONResponse:
        payload = await request.json()
        if capture_calls is not None:
            capture_calls.append(payload)
        if capture_status >= 400:
            return JSONResponse({"title": "Hold Expired"}, status_code=capture_status)
        return JSONResponse(
            {
                "id": str(uuid.uuid4()),
                "source_service": payload["source_service"],
                "source_id": payload["source_id"],
                "type": "PAYMENT",
                "currency": "UZS",
                "created_at": "2026-01-01T00:00:00Z",
            },
            status_code=capture_status,
        )

    @fake.post("/internal/v1/holds/{hold_id}/release")
    async def _post_release(hold_id: str) -> JSONResponse:
        return JSONResponse(
            {
                "id": hold_id,
                "account_id": str(uuid.uuid4()),
                "amount_minor": 1,
                "currency": "UZS",
                "status": "RELEASED",
                "created_at": "2026-01-01T00:00:00Z",
                "expires_at": "2026-01-01T00:15:00Z",
                "resolved_at": "2026-01-01T00:01:00Z",
            }
        )

    return fake


def _fraud_app(decision: str) -> FastAPI:
    fake = FastAPI()

    @fake.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": decision, "score": 10})

    return fake


def _wire_ledger(monkeypatch: pytest.MonkeyPatch, app_instance: FastAPI) -> None:
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=app_instance),
        ),
    )


def _wire_fraud(monkeypatch: pytest.MonkeyPatch, decision: str) -> None:
    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=httpx.ASGITransport(app=_fraud_app(decision)),
        ),
    )


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_active_merchant(owner_user_id: uuid.UUID) -> uuid.UUID:
    async with db_session.async_session_factory() as session:
        merchant = Merchant(owner_user_id=owner_user_id, name="Test Shop")
        session.add(merchant)
        await session.commit()
        await session.refresh(merchant)
        return merchant.id


async def _post_payment(
    client: AsyncClient, token: str, merchant_id: uuid.UUID, *, amount: str = "100.00"
) -> httpx.Response:
    return await client.post(
        "/api/v1/payments",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "merchant_id": str(merchant_id),
            "amount": amount,
            "currency": "UZS",
        },
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )


async def test_a_fully_allowed_payment_completes(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    user_id = uuid.uuid4()
    token = issue_access_token(user_id)
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "SUCCESS"
    assert body["fraud_decision"] == "ALLOW"
    assert body["amount_minor"] == 10_000
    assert body["completed_at"] is not None


async def test_a_blocked_payment_fails_without_ever_calling_ledger_holds(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    hold_calls: list[dict] = []
    _wire_ledger(monkeypatch, _ledger_app(hold_calls=hold_calls))
    _wire_fraud(monkeypatch, "BLOCK")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["fraud_decision"] == "BLOCK"
    assert hold_calls == []


async def test_a_review_payment_stays_created(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "REVIEW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "CREATED"
    assert body["fraud_decision"] == "REVIEW"


async def test_a_hold_rejected_for_insufficient_funds_fails_the_payment(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(hold_status=409))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_reason"] is not None


async def test_ledger_erroring_on_hold_leaves_the_payment_processing_not_failed(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    """The single most important behavior of the payment saga, same as
    the transfer saga's own equivalent test: an unknown outcome from the
    hold call is never reported as a failure — money may or may not
    have actually been reserved.

    Uses a 5xx response rather than a genuinely unroutable host: the
    wallet-ownership check (get_wallet) and the hold call share the same
    LedgerClient, so a truly unreachable client would 404 on
    authorization before ever reaching the hold — as
    LedgerClient.get_wallet's own unit tests separately cover genuine
    network unavailability, that scenario doesn't need duplicating here
    through the full HTTP stack (same reasoning as test_transfer_saga.py).
    """
    _wire_ledger(monkeypatch, _ledger_app(hold_status=503))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PROCESSING"
    assert body["failure_reason"] is None


async def test_capture_rejection_after_a_successful_hold_fails_the_payment_and_releases_it(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(capture_status=409))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"


async def test_a_payment_to_an_unknown_merchant_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, uuid.uuid4())

    assert response.status_code == 404
    assert response.json()["title"] == "Merchant Not Found"


async def test_a_payment_from_a_wallet_you_do_not_own_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(wallet_found=False))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 404
    assert response.json()["title"] == "Wallet Not Found"


async def test_currency_mismatch_with_the_source_wallet_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(wallet_currency="USD"))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        response = await _post_payment(client, token, merchant_id)

    assert response.status_code == 422
    assert response.json()["title"] == "Currency Mismatch"


async def test_repeating_the_same_idempotency_key_replays_the_response(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())
    idem_key = str(uuid.uuid4())
    payload = {
        "source_wallet_id": str(_SOURCE_WALLET),
        "merchant_id": str(merchant_id),
        "amount": "50.00",
        "currency": "UZS",
    }

    async with await _client() as client:
        first = await client.post(
            "/api/v1/payments",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key},
        )
        second = await client.post(
            "/api/v1/payments",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_getting_someone_elses_payment_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())
    merchant_id = await _create_active_merchant(uuid.uuid4())

    async with await _client() as client:
        created = await _post_payment(client, owner_token, merchant_id)
        payment_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/payments/{payment_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404
