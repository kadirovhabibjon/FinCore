import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db import session as db_session
from app.domain.idempotency import IdempotencyKey
from app.domain.transfer import FraudDecision, Transfer, TransferStatus
from app.services import ledger
from app.services.recovery import resolve_stuck_transfers

pytestmark = pytest.mark.usefixtures("migrated_database")

_SOURCE_WALLET = uuid.uuid4()
_DEST_WALLET = uuid.uuid4()


def _ledger_app(*, posting_status: int = 201) -> FastAPI:
    fake = FastAPI()

    @fake.post("/internal/v1/postings")
    async def _post_posting(request: Request) -> JSONResponse:
        payload = await request.json()
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


def _session() -> AsyncSession:
    return db_session.async_session_factory()


async def _create_stuck_transfer(
    *, status: TransferStatus = TransferStatus.PROCESSING, age_seconds: float = 120.0
) -> uuid.UUID:
    """Inserts a Transfer directly (bypassing the HTTP saga), already in
    `status` and `age_seconds` old, so recovery tests control staleness
    exactly instead of racing the saga's own timing.
    """
    async with _session() as session:
        idempotency_key = IdempotencyKey(
            user_id=uuid.uuid4(),
            key=str(uuid.uuid4()),
            request_fingerprint="fingerprint",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(idempotency_key)
        await session.flush()

        transfer = Transfer(
            initiator_user_id=idempotency_key.user_id,
            source_wallet_id=_SOURCE_WALLET,
            destination_wallet_id=_DEST_WALLET,
            amount_minor=10_000,
            currency="UZS",
            idempotency_key_id=idempotency_key.id,
            status=status,
            fraud_decision=FraudDecision.ALLOW,
        )
        session.add(transfer)
        await session.commit()
        await session.refresh(transfer)

        await session.execute(
            update(Transfer)
            .where(Transfer.id == transfer.id)
            .values(updated_at=datetime.now(UTC) - timedelta(seconds=age_seconds))
        )
        await session.commit()

        return transfer.id


async def test_a_stuck_transfer_is_completed_once_the_ledger_is_reachable_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    transfer_id = await _create_stuck_transfer()

    async with _session() as session:
        resolved = await resolve_stuck_transfers(session, stuck_after_seconds=60.0)

    assert [t.id for t in resolved] == [transfer_id]
    assert resolved[0].status == TransferStatus.COMPLETED
    assert resolved[0].completed_at is not None


async def test_a_stuck_transfer_the_ledger_rejects_is_marked_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _ledger_app(posting_status=409))
    transfer_id = await _create_stuck_transfer()

    async with _session() as session:
        resolved = await resolve_stuck_transfers(session, stuck_after_seconds=60.0)

    assert [t.id for t in resolved] == [transfer_id]
    assert resolved[0].status == TransferStatus.FAILED
    assert resolved[0].failure_reason is not None


async def test_a_transfer_still_within_the_grace_period_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    await _create_stuck_transfer(age_seconds=5.0)

    async with _session() as session:
        resolved = await resolve_stuck_transfers(session, stuck_after_seconds=60.0)

    assert resolved == []


async def test_a_transfer_that_is_not_processing_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _ledger_app())
    await _create_stuck_transfer(status=TransferStatus.COMPLETED)

    async with _session() as session:
        resolved = await resolve_stuck_transfers(session, stuck_after_seconds=60.0)

    assert resolved == []


async def test_a_still_unreachable_ledger_leaves_the_transfer_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://127.0.0.1:59995",
            internal_token=settings.internal_service_token,
            timeout_seconds=0.2,
        ),
    )
    transfer_id = await _create_stuck_transfer()

    async with _session() as session:
        resolved = await resolve_stuck_transfers(session, stuck_after_seconds=60.0)

    assert [t.id for t in resolved] == [transfer_id]
    assert resolved[0].status == TransferStatus.PROCESSING
