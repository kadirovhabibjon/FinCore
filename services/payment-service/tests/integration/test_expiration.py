import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select, update

from app.db import session as db_session
from app.domain.idempotency import IdempotencyKey
from app.domain.merchant import Merchant
from app.domain.outbox import OutboxEvent
from app.domain.payment import Payment, PaymentStatus
from app.services.expiration import expire_stale_payments

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _create_stale_created_payment(*, age_seconds: float = 1000.0) -> uuid.UUID:
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
            status=PaymentStatus.CREATED,
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)

        await session.execute(
            update(Payment)
            .where(Payment.id == payment.id)
            .values(created_at=datetime.now(UTC) - timedelta(seconds=age_seconds))
        )
        await session.commit()

        return payment.id


async def test_a_stale_created_payment_expires() -> None:
    payment_id = await _create_stale_created_payment()

    async with db_session.async_session_factory() as session:
        expired = await expire_stale_payments(session, stale_after_seconds=900.0)

    assert [p.id for p in expired] == [payment_id]
    assert expired[0].status == PaymentStatus.EXPIRED
    assert expired[0].failure_reason is not None

    events = []
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent).where(OutboxEvent.aggregate_id == str(payment_id))
        )
        events = list(result.scalars().all())
    assert len(events) == 1
    assert events[0].event_type == "payment.failed"
    assert events[0].payload["status"] == "EXPIRED"


async def test_a_payment_still_within_the_review_window_is_left_alone() -> None:
    await _create_stale_created_payment(age_seconds=5.0)

    async with db_session.async_session_factory() as session:
        expired = await expire_stale_payments(session, stale_after_seconds=900.0)

    assert expired == []


async def test_a_processing_payment_is_never_expired_only_created_ones_are() -> None:
    """The spec's own state machine only allows EXPIRED from CREATED,
    never from PROCESSING — a PROCESSING payment with a stuck hold is
    the recovery worker's concern, not the expiration worker's.
    """
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
        )
        session.add(payment)
        await session.commit()
        await session.refresh(payment)
        await session.execute(
            update(Payment)
            .where(Payment.id == payment.id)
            .values(created_at=datetime.now(UTC) - timedelta(seconds=1000.0))
        )
        await session.commit()

    async with db_session.async_session_factory() as session:
        expired = await expire_stale_payments(session, stale_after_seconds=900.0)

    assert expired == []
