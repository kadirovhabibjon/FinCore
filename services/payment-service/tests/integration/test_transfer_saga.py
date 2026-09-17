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


def _ledger_app(
    *,
    wallet_currency: str = "UZS",
    wallet_found: bool = True,
    posting_status: int = 201,
    posting_calls: list[dict] | None = None,
) -> FastAPI:
    fake = FastAPI()

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _get_wallet(wallet_id: str) -> JSONResponse:
        if not wallet_found:
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
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

    @fake.post("/internal/v1/postings")
    async def _post_posting(request: Request) -> JSONResponse:
        payload = await request.json()
        if posting_calls is not None:
            posting_calls.append(payload)
        if posting_status >= 400:
            return JSONResponse(
                {"title": "Insufficient Funds", "status": posting_status},
                status_code=posting_status,
            )
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


def _wire_ledger_unreachable(monkeypatch: pytest.MonkeyPatch) -> None:
    """No fake transport: a real connection attempt against a port
    nothing is listening on — genuine network-level unavailability, the
    scenario the "unknown outcome" branch exists for.
    """
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://127.0.0.1:59998",
            internal_token=settings.internal_service_token,
            timeout_seconds=0.2,
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


async def test_a_fully_allowed_transfer_completes(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED"
    assert body["fraud_decision"] == "ALLOW"
    assert body["amount_minor"] == 10_000
    assert body["completed_at"] is not None


async def test_a_blocked_transfer_fails_without_calling_ledger(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    posting_calls: list[dict] = []
    _wire_ledger(monkeypatch, _ledger_app(posting_calls=posting_calls))
    _wire_fraud(monkeypatch, "BLOCK")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 201  # the API call itself succeeded
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["fraud_decision"] == "BLOCK"
    assert body["failure_reason"] is not None
    assert posting_calls == []  # the saga never reached the ledger call


async def test_a_review_transfer_stays_pending(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "REVIEW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PENDING"
    assert body["fraud_decision"] == "REVIEW"


async def test_a_ledger_business_rejection_fails_the_transfer(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(posting_status=409))  # insufficient funds
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "FAILED"
    assert body["failure_reason"] is not None


async def test_ledger_service_erroring_leaves_the_transfer_processing_not_failed(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    """The single most important behavior in the whole saga (spec Section
    10.1's revision notes): an unknown ledger outcome is never reported
    as a failure. A 5xx from the posting call — money may or may not have
    actually moved — must leave the transfer PROCESSING, not FAILED.

    (LedgerClient's own unit tests separately cover the genuine
    network-unreachable case against a real unroutable port; that
    scenario is equivalent from this saga's point of view — both map to
    PostingOutcome.UNKNOWN — so it isn't duplicated here through the
    full HTTP stack.)
    """
    error_app = FastAPI()

    @error_app.get("/api/v1/wallets/{wallet_id}")
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

    @error_app.post("/internal/v1/postings")
    async def _post_posting() -> JSONResponse:
        return JSONResponse({"title": "Internal Server Error"}, status_code=503)

    _wire_ledger(monkeypatch, error_app)
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "PROCESSING"  # never FAILED
    assert body["failure_reason"] is None


async def test_transfer_to_the_same_wallet_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_SOURCE_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 422
    assert response.json()["title"] == "Same Wallet Transfer"


async def test_transfer_from_a_wallet_you_do_not_own_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(wallet_found=False))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 404
    assert response.json()["title"] == "Wallet Not Found"


async def test_currency_mismatch_with_the_source_wallet_is_rejected(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(wallet_currency="USD"))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "100.00",
                "currency": "UZS",
            },
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
        )

    assert response.status_code == 422
    assert response.json()["title"] == "Currency Mismatch"


async def test_repeating_the_same_idempotency_key_replays_the_response(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())
    idem_key = str(uuid.uuid4())
    payload = {
        "source_wallet_id": str(_SOURCE_WALLET),
        "destination_wallet_id": str(_DEST_WALLET),
        "amount": "50.00",
        "currency": "UZS",
    }

    async with await _client() as client:
        first = await client.post(
            "/api/v1/transfers",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key},
        )
        second = await client.post(
            "/api/v1/transfers",
            json=payload,
            headers={"Authorization": f"Bearer {token}", "Idempotency-Key": idem_key},
        )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["id"] == second.json()["id"]


async def test_getting_someone_elses_transfer_returns_not_found(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        created = await client.post(
            "/api/v1/transfers",
            json={
                "source_wallet_id": str(_SOURCE_WALLET),
                "destination_wallet_id": str(_DEST_WALLET),
                "amount": "10.00",
                "currency": "UZS",
            },
            headers={
                "Authorization": f"Bearer {owner_token}",
                "Idempotency-Key": str(uuid.uuid4()),
            },
        )
        transfer_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/transfers/{transfer_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404
