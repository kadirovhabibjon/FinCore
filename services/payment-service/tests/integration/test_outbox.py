import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.domain.idempotency import IdempotencyKey
from app.domain.outbox import OutboxEvent
from app.domain.transfer import FraudDecision, Transfer, TransferStatus
from app.main import app
from app.repositories.transfer_repository import TransferRepository
from app.services import fraud, ledger
from app.services.transfers import attempt_posting_and_resolve

pytestmark = pytest.mark.usefixtures("migrated_database")

_SOURCE_WALLET = uuid.uuid4()
_DEST_WALLET = uuid.uuid4()


def _ledger_app(*, wallet_found: bool = True, posting_status: int = 201) -> FastAPI:
    fake = FastAPI()

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _get_wallet(wallet_id: str) -> JSONResponse:
        if not wallet_found:
            return JSONResponse({"title": "Wallet Not Found"}, status_code=404)
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
        if posting_status >= 400:
            return JSONResponse({"title": "Insufficient Funds"}, status_code=posting_status)
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


async def _create_transfer(client: AsyncClient, token: str) -> httpx.Response:
    return await client.post(
        "/api/v1/transfers",
        json={
            "source_wallet_id": str(_SOURCE_WALLET),
            "destination_wallet_id": str(_DEST_WALLET),
            "amount": "10.00",
            "currency": "UZS",
        },
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )


async def _outbox_rows_for(transfer_id: str) -> list[OutboxEvent]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == transfer_id)
        )
        return list(result.scalars().all())


async def test_a_completed_transfer_writes_a_transfer_completed_outbox_event(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await _create_transfer(client, token)

    transfer_id = response.json()["id"]
    rows = await _outbox_rows_for(transfer_id)

    assert len(rows) == 1
    assert rows[0].event_type == "transfer.completed"
    assert rows[0].aggregate_type == "Transfer"
    assert rows[0].published_at is None
    assert rows[0].payload["status"] == "COMPLETED"
    assert rows[0].payload["amount_minor"] == 1_000


async def test_a_fraud_blocked_transfer_writes_a_transfer_failed_outbox_event(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "BLOCK")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await _create_transfer(client, token)

    transfer_id = response.json()["id"]
    rows = await _outbox_rows_for(transfer_id)

    assert len(rows) == 1
    assert rows[0].event_type == "transfer.failed"
    assert rows[0].payload["failure_reason"] == "blocked by fraud check"


async def test_a_ledger_rejected_transfer_writes_a_transfer_failed_outbox_event(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(posting_status=409))
    _wire_fraud(monkeypatch, "ALLOW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await _create_transfer(client, token)

    transfer_id = response.json()["id"]
    rows = await _outbox_rows_for(transfer_id)

    assert len(rows) == 1
    assert rows[0].event_type == "transfer.failed"


async def test_a_transfer_under_review_writes_no_outbox_event(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    _wire_fraud(monkeypatch, "REVIEW")
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await _create_transfer(client, token)

    transfer_id = response.json()["id"]
    rows = await _outbox_rows_for(transfer_id)

    assert rows == []


async def test_an_unresolved_ledger_outcome_writes_no_outbox_event(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
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
        response = await _create_transfer(client, token)

    transfer_id = response.json()["id"]
    rows = await _outbox_rows_for(transfer_id)

    assert rows == []


async def test_two_concurrent_resolutions_of_the_same_transfer_write_exactly_one_outbox_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates the saga's own call and the recovery worker racing to
    resolve the same PROCESSING transfer (app/services/transfers.py's
    `attempt_posting_and_resolve` docstring) — only the caller whose
    UPDATE actually applies may write the outbox event, or a transfer
    would end up with two transfer.completed events for one completion.
    """
    _wire_ledger(monkeypatch, _ledger_app())

    async with db_session.async_session_factory() as setup_session:
        idempotency_key = IdempotencyKey(
            user_id=uuid.uuid4(),
            key=str(uuid.uuid4()),
            request_fingerprint="fp",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        setup_session.add(idempotency_key)
        await setup_session.flush()
        transfer = Transfer(
            initiator_user_id=idempotency_key.user_id,
            source_wallet_id=_SOURCE_WALLET,
            destination_wallet_id=_DEST_WALLET,
            amount_minor=5_000,
            currency="UZS",
            idempotency_key_id=idempotency_key.id,
            status=TransferStatus.PROCESSING,
            fraud_decision=FraudDecision.ALLOW,
        )
        setup_session.add(transfer)
        await setup_session.commit()
        await setup_session.refresh(transfer)
        transfer_id = transfer.id

    async def _resolve_once() -> None:
        async with db_session.async_session_factory() as session:
            repository = TransferRepository(session)
            row = await repository.get(transfer_id)
            assert row is not None
            await attempt_posting_and_resolve(session, repository, row)

    await asyncio.gather(_resolve_once(), _resolve_once())

    rows = await _outbox_rows_for(str(transfer_id))
    assert len(rows) == 1
    assert rows[0].event_type == "transfer.completed"
