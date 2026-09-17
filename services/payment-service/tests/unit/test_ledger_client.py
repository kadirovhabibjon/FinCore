import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.ledger import LedgerClient, PostingOutcome


def _client(transport: httpx.ASGITransport | None = None, **overrides) -> LedgerClient:
    defaults = {
        "base_url": "http://ledger",
        "internal_token": "test-token",
        "timeout_seconds": 0.2,
    }
    defaults.update(overrides)
    return LedgerClient(transport=transport, **defaults)


def _posting_app(status_code: int) -> httpx.ASGITransport:
    app = FastAPI()

    @app.post("/internal/v1/postings")
    async def _post(request: Request) -> JSONResponse:
        payload = await request.json()
        if status_code >= 400:
            return JSONResponse({"title": "rejected"}, status_code=status_code)
        return JSONResponse(
            {
                "id": str(uuid.uuid4()),
                "source_service": payload["source_service"],
                "source_id": payload["source_id"],
                "type": payload["type"],
                "currency": payload["currency"],
                "created_at": "2026-01-01T00:00:00Z",
            },
            status_code=status_code,
        )

    return httpx.ASGITransport(app=app)


async def test_create_posting_succeeds() -> None:
    client = _client(transport=_posting_app(201))

    result = await client.create_posting(
        source_service="payment-service",
        source_id="src-1",
        type="TRANSFER",
        currency="UZS",
        entries=[],
    )

    assert result.outcome == PostingOutcome.SUCCESS
    assert result.posting_id is not None


async def test_create_posting_treats_insufficient_funds_as_business_rejection() -> None:
    client = _client(transport=_posting_app(409))

    result = await client.create_posting(
        source_service="payment-service",
        source_id="src-2",
        type="TRANSFER",
        currency="UZS",
        entries=[],
    )

    assert result.outcome == PostingOutcome.BUSINESS_REJECTION
    assert result.failure_reason is not None


async def test_create_posting_treats_a_5xx_as_unknown_outcome() -> None:
    client = _client(transport=_posting_app(503))

    result = await client.create_posting(
        source_service="payment-service",
        source_id="src-3",
        type="TRANSFER",
        currency="UZS",
        entries=[],
    )

    assert result.outcome == PostingOutcome.UNKNOWN


async def test_create_posting_treats_an_unreachable_host_as_unknown_outcome() -> None:
    """A real connection attempt against a port nothing is listening on —
    genuine network-level unavailability, not a mocked exception. This is
    the scenario the transfer saga's "never mark FAILED on an unknown
    ledger outcome" rule exists for (spec Section 10.1's revision notes).
    """
    client = _client(transport=None, base_url="http://127.0.0.1:59997")

    result = await client.create_posting(
        source_service="payment-service",
        source_id="src-4",
        type="TRANSFER",
        currency="UZS",
        entries=[],
    )

    assert result.outcome == PostingOutcome.UNKNOWN


async def test_get_wallet_returns_none_when_not_found() -> None:
    app = FastAPI()

    @app.get("/api/v1/wallets/{wallet_id}")
    async def _get(wallet_id: str) -> JSONResponse:
        return JSONResponse({"title": "not found"}, status_code=404)

    client = _client(transport=httpx.ASGITransport(app=app))

    result = await client.get_wallet(uuid.uuid4(), user_bearer_token="token")

    assert result is None


async def test_get_wallet_returns_wallet_info_when_found() -> None:
    wallet_id = uuid.uuid4()
    app = FastAPI()

    @app.get("/api/v1/wallets/{requested_id}")
    async def _get(requested_id: str) -> JSONResponse:
        return JSONResponse(
            {
                "id": requested_id,
                "currency": "UZS",
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "balance_minor": 0,
                "held_minor": 0,
            }
        )

    client = _client(transport=httpx.ASGITransport(app=app))

    result = await client.get_wallet(wallet_id, user_bearer_token="token")

    assert result is not None
    assert result.id == wallet_id
    assert result.currency == "UZS"


async def test_get_wallet_returns_none_when_ledger_is_unreachable() -> None:
    client = _client(transport=None, base_url="http://127.0.0.1:59996")

    result = await client.get_wallet(uuid.uuid4(), user_bearer_token="token")

    assert result is None
