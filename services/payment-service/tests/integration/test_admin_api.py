import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.domain.merchant import Merchant
from app.domain.outbox import OutboxEvent
from app.main import app
from app.services import fraud, ledger
from app.services.expiration import expire_stale_payments

pytestmark = pytest.mark.usefixtures("migrated_database")

_SOURCE_WALLET = uuid.uuid4()
_DEST_WALLET = uuid.uuid4()


class _LedgerCalls:
    def __init__(self) -> None:
        self.postings: list[dict] = []
        self.holds: list[dict] = []
        self.captures: list[dict] = []


def _ledger_app(calls: _LedgerCalls) -> FastAPI:
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
        calls.postings.append(payload)
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
        calls.holds.append(payload)
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
        calls.captures.append(payload)
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


def _fraud_app(decision: str) -> FastAPI:
    fake = FastAPI()

    @fake.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": decision, "score": 50})

    return fake


@pytest.fixture
def ledger_calls(monkeypatch: pytest.MonkeyPatch) -> _LedgerCalls:
    calls = _LedgerCalls()
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_ledger_app(calls)),
        ),
    )
    return calls


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


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _post_transfer(client: AsyncClient, token: str) -> dict:
    response = await client.post(
        "/api/v1/transfers",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "destination_wallet_id": str(_DEST_WALLET),
            "amount": "100.00",
            "currency": "UZS",
        },
        headers={**_auth(token), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    return response.json()


async def _post_payment(client: AsyncClient, token: str) -> dict:
    async with db_session.async_session_factory() as session:
        merchant = Merchant(owner_user_id=uuid.uuid4(), name="Review Shop")
        session.add(merchant)
        await session.commit()
        merchant_id = merchant.id
    response = await client.post(
        "/api/v1/payments",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "merchant_id": str(merchant_id),
            "amount": "50.00",
            "currency": "UZS",
        },
        headers={**_auth(token), "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    return response.json()


async def _outbox_event_types(aggregate_id: str) -> list[str]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent.event_type).where(OutboxEvent.aggregate_id == aggregate_id)
        )
        return list(result.scalars().all())


async def test_the_queue_lists_items_awaiting_review_to_staff_only(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "REVIEW")
    customer_id = uuid.uuid4()
    customer = issue_access_token(customer_id)
    support = issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"])

    async with _client() as client:
        transfer = await _post_transfer(client, customer)
        payment = await _post_payment(client, customer)
        queue = await client.get("/api/v1/admin/reviews", headers=_auth(support))
        forbidden = await client.get("/api/v1/admin/reviews", headers=_auth(customer))

    assert queue.status_code == 200
    items = queue.json()
    assert [item["id"] for item in items] == [transfer["id"], payment["id"]]
    assert [item["type"] for item in items] == ["TRANSFER", "PAYMENT"]
    assert items[0]["counterparty_id"] == str(_DEST_WALLET)
    assert all(item["initiator_user_id"] == str(customer_id) for item in items)
    assert all(item["fraud_decision"] == "REVIEW" for item in items)
    assert forbidden.status_code == 403
    assert ledger_calls.postings == ledger_calls.holds == []


async def test_approving_a_transfer_runs_the_rest_of_the_saga(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "REVIEW")
    customer = issue_access_token(uuid.uuid4())
    admin_id = uuid.uuid4()
    admin = issue_access_token(admin_id, ["USER", "ADMIN"])

    async with _client() as client:
        transfer = await _post_transfer(client, customer)
        decided = await client.post(
            f"/api/v1/admin/reviews/{transfer['id']}",
            json={"decision": "APPROVE"},
            headers=_auth(admin),
        )
        queue = (await client.get("/api/v1/admin/reviews", headers=_auth(admin))).json()
        seen_by_customer = (
            await client.get(f"/api/v1/transfers/{transfer['id']}", headers=_auth(customer))
        ).json()

    assert decided.status_code == 200
    body = decided.json()
    assert body["status"] == "COMPLETED"
    assert body["reviewed_by_user_id"] == str(admin_id)
    assert body["reviewed_at"] is not None
    assert body["fraud_decision"] == "REVIEW"
    assert [p["source_id"] for p in ledger_calls.postings] == [transfer["id"]]
    assert queue == []
    assert seen_by_customer["status"] == "COMPLETED"
    assert await _outbox_event_types(transfer["id"]) == ["transfer.completed"]


async def test_approving_a_payment_holds_and_captures(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "REVIEW")
    customer = issue_access_token(uuid.uuid4())
    admin = issue_access_token(uuid.uuid4(), ["USER", "ADMIN"])

    async with _client() as client:
        payment = await _post_payment(client, customer)
        decided = await client.post(
            f"/api/v1/admin/reviews/{payment['id']}",
            json={"decision": "APPROVE"},
            headers=_auth(admin),
        )

    assert decided.json()["status"] == "SUCCESS"
    assert [h["source_id"] for h in ledger_calls.holds] == [payment["id"]]
    assert [c["source_id"] for c in ledger_calls.captures] == [payment["id"]]


async def test_rejecting_fails_the_operation_without_touching_the_ledger(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "REVIEW")
    customer = issue_access_token(uuid.uuid4())
    admin = issue_access_token(uuid.uuid4(), ["USER", "ADMIN"])

    async with _client() as client:
        transfer = await _post_transfer(client, customer)
        payment = await _post_payment(client, customer)
        rejected_transfer = await client.post(
            f"/api/v1/admin/reviews/{transfer['id']}",
            json={"decision": "REJECT"},
            headers=_auth(admin),
        )
        rejected_payment = await client.post(
            f"/api/v1/admin/reviews/{payment['id']}",
            json={"decision": "REJECT"},
            headers=_auth(admin),
        )

    for response in (rejected_transfer, rejected_payment):
        assert response.status_code == 200
        assert response.json()["status"] == "FAILED"
        assert response.json()["failure_reason"] == "rejected in fraud review"
    assert ledger_calls.postings == ledger_calls.holds == []
    assert await _outbox_event_types(transfer["id"]) == ["transfer.failed"]
    assert await _outbox_event_types(payment["id"]) == ["payment.failed"]


async def test_only_one_decision_wins_and_only_admins_decide(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "REVIEW")
    customer = issue_access_token(uuid.uuid4())
    support = issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"])
    admin = issue_access_token(uuid.uuid4(), ["USER", "ADMIN"])

    async with _client() as client:
        transfer = await _post_transfer(client, customer)
        by_support = await client.post(
            f"/api/v1/admin/reviews/{transfer['id']}",
            json={"decision": "APPROVE"},
            headers=_auth(support),
        )
        first = await client.post(
            f"/api/v1/admin/reviews/{transfer['id']}",
            json={"decision": "REJECT"},
            headers=_auth(admin),
        )
        second = await client.post(
            f"/api/v1/admin/reviews/{transfer['id']}",
            json={"decision": "APPROVE"},
            headers=_auth(admin),
        )
        unknown = await client.post(
            f"/api/v1/admin/reviews/{uuid.uuid4()}",
            json={"decision": "APPROVE"},
            headers=_auth(admin),
        )

    assert by_support.status_code == 403
    assert first.status_code == 200
    assert second.status_code == 409
    assert unknown.status_code == 404
    assert ledger_calls.postings == []


async def test_an_operation_that_was_never_in_review_cannot_be_decided(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "ALLOW")
    customer = issue_access_token(uuid.uuid4())
    admin = issue_access_token(uuid.uuid4(), ["USER", "ADMIN"])

    async with _client() as client:
        transfer = await _post_transfer(client, customer)
        response = await client.post(
            f"/api/v1/admin/reviews/{transfer['id']}",
            json={"decision": "REJECT"},
            headers=_auth(admin),
        )

    assert transfer["status"] == "COMPLETED"
    assert response.status_code == 409


async def test_an_expired_payment_can_no_longer_be_approved(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "REVIEW")
    customer = issue_access_token(uuid.uuid4())
    admin = issue_access_token(uuid.uuid4(), ["USER", "ADMIN"])

    async with _client() as client:
        payment = await _post_payment(client, customer)
        async with db_session.async_session_factory() as session:
            expired = await expire_stale_payments(session, stale_after_seconds=0)
        response = await client.post(
            f"/api/v1/admin/reviews/{payment['id']}",
            json={"decision": "APPROVE"},
            headers=_auth(admin),
        )

    assert [p.id for p in expired] == [uuid.UUID(payment["id"])]
    assert response.status_code == 409
    assert ledger_calls.holds == []


async def test_staff_see_every_users_transactions_with_filters(
    monkeypatch: pytest.MonkeyPatch, issue_access_token, ledger_calls: _LedgerCalls
) -> None:
    _wire_fraud(monkeypatch, "ALLOW")
    alice_id, bob_id = uuid.uuid4(), uuid.uuid4()
    alice = issue_access_token(alice_id)
    bob = issue_access_token(bob_id)
    support = issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"])

    async with _client() as client:
        alice_transfer = await _post_transfer(client, alice)
        bob_payment = await _post_payment(client, bob)

        everything = await client.get("/api/v1/admin/transactions", headers=_auth(support))
        only_bob = await client.get(
            "/api/v1/admin/transactions", params={"user_id": str(bob_id)}, headers=_auth(support)
        )
        only_transfers = await client.get(
            "/api/v1/admin/transactions", params={"type": "TRANSFER"}, headers=_auth(support)
        )
        succeeded = await client.get(
            "/api/v1/admin/transactions", params={"status": "SUCCESS"}, headers=_auth(support)
        )
        paged = await client.get(
            "/api/v1/admin/transactions",
            params={"limit": 1, "offset": 1},
            headers=_auth(support),
        )
        forbidden = await client.get("/api/v1/admin/transactions", headers=_auth(alice))

    assert [t["id"] for t in everything.json()] == [bob_payment["id"], alice_transfer["id"]]
    assert [t["id"] for t in only_bob.json()] == [bob_payment["id"]]
    assert [t["id"] for t in only_transfers.json()] == [alice_transfer["id"]]
    assert [t["id"] for t in succeeded.json()] == [bob_payment["id"]]
    assert [t["id"] for t in paged.json()] == [alice_transfer["id"]]
    assert forbidden.status_code == 403
