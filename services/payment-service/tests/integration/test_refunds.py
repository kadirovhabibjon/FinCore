import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.main import app
from app.services import fraud, ledger

pytestmark = pytest.mark.usefixtures("migrated_database")

_SOURCE_WALLET = uuid.uuid4()
_MERCHANT_ACCOUNT_ID = uuid.uuid4()


def _full_ledger_app(*, posting_status: int = 201) -> FastAPI:
    """Serves everything a payment (hold + capture) and a refund
    (system account lookup + posting) need from ledger-service.
    """
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

    @fake.get("/internal/v1/accounts/system")
    async def _get_system_account(kind: str, currency: str) -> JSONResponse:
        return JSONResponse({"id": str(_MERCHANT_ACCOUNT_ID), "kind": kind, "currency": currency})

    @fake.post("/internal/v1/postings")
    async def _post_posting(request: Request) -> JSONResponse:
        payload = await request.json()
        if posting_status >= 400:
            return JSONResponse({"title": "rejected"}, status_code=posting_status)
        return JSONResponse(
            {
                "id": str(uuid.uuid4()),
                "source_service": payload["source_service"],
                "source_id": payload["source_id"],
                "type": payload["type"],
                "currency": payload["currency"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            status_code=posting_status,
        )

    return fake


def _fraud_app_allow() -> FastAPI:
    fake = FastAPI()

    @fake.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": "ALLOW", "score": 0})

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


def _wire_fraud_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=httpx.ASGITransport(app=_fraud_app_allow()),
        ),
    )


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _create_merchant(client: AsyncClient, owner_token: str) -> str:
    response = await client.post(
        "/api/v1/merchants", json={"name": "Test Shop"}, headers=_auth(owner_token)
    )
    return response.json()["id"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_successful_payment(
    client: AsyncClient, payer_token: str, merchant_id: str, *, amount: str = "100.00"
) -> dict:
    response = await client.post(
        "/api/v1/payments",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "merchant_id": merchant_id,
            "amount": amount,
            "currency": "UZS",
        },
        headers={**_auth(payer_token), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "SUCCESS"
    return response.json()


async def _outbox_events_for(aggregate_id: str) -> list[OutboxEvent]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == aggregate_id)
        )
        return list(result.scalars().all())


async def test_a_full_refund_marks_the_payment_refunded(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)
        payment = await _create_successful_payment(client, payer_token, merchant_id)

        response = await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json={"amount": "100.00", "reason": "customer request"},
            headers={**_auth(merchant_owner_token), "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["amount_minor"] == 10_000

    events = await _outbox_events_for(payment["id"])
    refund_events = [e for e in events if e.event_type == "payment.refunded"]
    assert len(refund_events) == 1
    assert refund_events[0].payload["status"] == "REFUNDED"


async def test_a_partial_refund_marks_the_payment_partially_refunded(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)
        payment = await _create_successful_payment(client, payer_token, merchant_id)

        refund_response = await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json={"amount": "40.00"},
            headers={**_auth(merchant_owner_token), "Idempotency-Key": str(uuid.uuid4())},
        )
        payment_response = await client.get(
            f"/api/v1/payments/{payment['id']}", headers=_auth(payer_token)
        )

    assert refund_response.status_code == 201
    assert refund_response.json()["status"] == "COMPLETED"

    payment_body = payment_response.json()
    assert payment_body["status"] == "PARTIALLY_REFUNDED"
    assert payment_body["refunded_amount_minor"] == 4_000


async def test_two_partial_refunds_summing_to_the_full_amount_complete_the_refund(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)
        payment = await _create_successful_payment(client, payer_token, merchant_id)

        await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json={"amount": "60.00"},
            headers={**_auth(merchant_owner_token), "Idempotency-Key": str(uuid.uuid4())},
        )
        await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json={"amount": "40.00"},
            headers={**_auth(merchant_owner_token), "Idempotency-Key": str(uuid.uuid4())},
        )
        payment_response = await client.get(
            f"/api/v1/payments/{payment['id']}", headers=_auth(payer_token)
        )

    payment_body = payment_response.json()
    assert payment_body["status"] == "REFUNDED"
    assert payment_body["refunded_amount_minor"] == 10_000


async def test_a_refund_exceeding_the_remaining_amount_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)
        payment = await _create_successful_payment(client, payer_token, merchant_id)

        response = await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json={"amount": "150.00"},
            headers={**_auth(merchant_owner_token), "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 422
    assert response.json()["title"] == "Refund Exceeds Remaining Amount"


async def test_refunding_a_payment_that_was_never_captured_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())

    fraud_review_app = FastAPI()

    @fraud_review_app.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": "REVIEW", "score": 50})

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)

        monkeypatch.setattr(
            fraud,
            "fraud_client",
            fraud.FraudClient(
                base_url="http://fraud",
                internal_token=settings.internal_service_token,
                timeout_seconds=2.0,
                fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
                transport=httpx.ASGITransport(app=fraud_review_app),
            ),
        )
        created = await client.post(
            "/api/v1/payments",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "merchant_id": merchant_id,
                "amount": "10.00",
                "currency": "UZS",
            },
            headers={**_auth(payer_token), "Idempotency-Key": str(uuid.uuid4())},
        )
        assert created.json()["status"] == "CREATED"

        response = await client.post(
            f"/api/v1/payments/{created.json()['id']}/refunds",
            json={"amount": "10.00"},
            headers={**_auth(merchant_owner_token), "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 409
    assert response.json()["title"] == "Payment Not Eligible For Refund"


async def test_refunding_someone_elses_payment_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)
        payment = await _create_successful_payment(client, payer_token, merchant_id)

        response = await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json={"amount": "10.00"},
            headers={**_auth(intruder_token), "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 404


async def test_repeating_the_same_refund_idempotency_key_replays_the_response(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _full_ledger_app())
    _wire_fraud_allow(monkeypatch)
    payer_token = issue_access_token(uuid.uuid4())
    merchant_owner_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        merchant_id = await _create_merchant(client, merchant_owner_token)
        payment = await _create_successful_payment(client, payer_token, merchant_id)

        idem_key = str(uuid.uuid4())
        payload = {"amount": "25.00"}
        first = await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json=payload,
            headers={**_auth(merchant_owner_token), "Idempotency-Key": idem_key},
        )
        second = await client.post(
            f"/api/v1/payments/{payment['id']}/refunds",
            json=payload,
            headers={**_auth(merchant_owner_token), "Idempotency-Key": idem_key},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
