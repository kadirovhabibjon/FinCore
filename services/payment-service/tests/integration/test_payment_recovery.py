import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import update

from app.core.config import settings
from app.db import session as db_session
from app.domain.idempotency import IdempotencyKey
from app.domain.merchant import Merchant
from app.domain.payment import Payment, PaymentStatus
from app.domain.refund import Refund, RefundStatus
from app.domain.transfer import FraudDecision
from app.services import ledger
from app.services.recovery import resolve_stuck_payments, resolve_stuck_refunds

pytestmark = pytest.mark.usefixtures("migrated_database")


def _capture_only_ledger_app() -> FastAPI:
    """A payment stuck PROCESSING with a hold already recorded only
    needs the capture retried — this app doesn't even implement
    /internal/v1/holds, so a test that hits it by mistake fails loudly.
    """
    fake = FastAPI()

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


def _posting_only_ledger_app() -> FastAPI:
    fake = FastAPI()
    merchant_account_id = uuid.uuid4()

    @fake.get("/internal/v1/accounts/system")
    async def _get_system_account(kind: str, currency: str) -> JSONResponse:
        return JSONResponse({"id": str(merchant_account_id), "kind": kind, "currency": currency})

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


async def _create_stuck_payment(*, hold_id: uuid.UUID, age_seconds: float = 120.0) -> uuid.UUID:
    async with db_session.async_session_factory() as session:
        idempotency_key = IdempotencyKey(
            user_id=uuid.uuid4(),
            key=str(uuid.uuid4()),
            request_fingerprint="fp",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(idempotency_key)
        await session.flush()
        merchant = Merchant(owner_user_id=uuid.uuid4(), name="Test Shop")
        session.add(merchant)
        await session.flush()

        payment = Payment(
            initiator_user_id=idempotency_key.user_id,
            source_wallet_id=uuid.uuid4(),
            merchant_id=merchant.id,
            amount_minor=10_000,
            currency="UZS",
            idempotency_key_id=idempotency_key.id,
            status=PaymentStatus.PROCESSING,
            fraud_decision=FraudDecision.ALLOW,
            hold_id=hold_id,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)

        await session.execute(
            update(Payment)
            .where(Payment.id == payment.id)
            .values(updated_at=datetime.now(UTC) - timedelta(seconds=age_seconds))
        )
        await session.commit()
        return payment.id


async def _create_stuck_refund(*, age_seconds: float = 120.0) -> tuple[uuid.UUID, uuid.UUID]:
    async with db_session.async_session_factory() as session:
        payment_idempotency_key = IdempotencyKey(
            user_id=uuid.uuid4(),
            key=str(uuid.uuid4()),
            request_fingerprint="fp-payment",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(payment_idempotency_key)
        await session.flush()
        merchant = Merchant(owner_user_id=uuid.uuid4(), name="Test Shop")
        session.add(merchant)
        await session.flush()

        payment = Payment(
            initiator_user_id=payment_idempotency_key.user_id,
            source_wallet_id=uuid.uuid4(),
            merchant_id=merchant.id,
            amount_minor=10_000,
            currency="UZS",
            idempotency_key_id=payment_idempotency_key.id,
            status=PaymentStatus.SUCCESS,
            fraud_decision=FraudDecision.ALLOW,
            hold_id=uuid.uuid4(),
            completed_at=datetime.now(UTC),
        )
        session.add(payment)
        await session.flush()

        refund_idempotency_key = IdempotencyKey(
            user_id=uuid.uuid4(),
            key=str(uuid.uuid4()),
            request_fingerprint="fp-refund",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
        session.add(refund_idempotency_key)
        await session.flush()

        refund = Refund(
            payment_id=payment.id,
            amount_minor=5_000,
            idempotency_key_id=refund_idempotency_key.id,
            status=RefundStatus.PENDING,
        )
        session.add(refund)
        await session.commit()
        await session.refresh(refund)

        await session.execute(
            update(Refund)
            .where(Refund.id == refund.id)
            .values(updated_at=datetime.now(UTC) - timedelta(seconds=age_seconds))
        )
        await session.commit()
        return refund.id, payment.id


async def test_resolve_stuck_payments_resumes_from_an_existing_hold_straight_to_capture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _capture_only_ledger_app())
    hold_id = uuid.uuid4()
    payment_id = await _create_stuck_payment(hold_id=hold_id)

    async with db_session.async_session_factory() as session:
        resolved = await resolve_stuck_payments(session, stuck_after_seconds=60.0)

    assert [p.id for p in resolved] == [payment_id]
    assert resolved[0].status == PaymentStatus.SUCCESS
    assert resolved[0].hold_id == hold_id


async def test_resolve_stuck_payments_leaves_recent_ones_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _capture_only_ledger_app())
    await _create_stuck_payment(hold_id=uuid.uuid4(), age_seconds=5.0)

    async with db_session.async_session_factory() as session:
        resolved = await resolve_stuck_payments(session, stuck_after_seconds=60.0)

    assert resolved == []


async def test_resolve_stuck_refunds_completes_a_pending_refund_and_updates_the_payment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_ledger(monkeypatch, _posting_only_ledger_app())
    refund_id, payment_id = await _create_stuck_refund()

    async with db_session.async_session_factory() as session:
        resolved = await resolve_stuck_refunds(session, stuck_after_seconds=60.0)

    assert [r.id for r in resolved] == [refund_id]
    assert resolved[0].status == RefundStatus.COMPLETED

    async with db_session.async_session_factory() as session:
        payment = await session.get(Payment, payment_id)
        assert payment is not None
        assert payment.status == PaymentStatus.PARTIALLY_REFUNDED
        assert payment.refunded_amount_minor == 5_000
