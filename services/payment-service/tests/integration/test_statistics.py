"""Money in and out per month: what is counted, and into which month."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import session as db_session
from app.domain.idempotency import IdempotencyKey
from app.domain.merchant import Merchant
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus
from app.main import app
from app.services.statistics import month_keys, monthly_totals

pytestmark = pytest.mark.usefixtures("migrated_database")

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=UTC)


def test_month_keys_cross_a_year_boundary_oldest_first() -> None:
    assert month_keys(datetime(2026, 2, 15, tzinfo=UTC), 4) == [
        "2025-11",
        "2025-12",
        "2026-01",
        "2026-02",
    ]
    assert month_keys(NOW, 1) == ["2026-10"]
    # 23:30 in Tashkent on 30 Sep is still September in UTC.
    tashkent = datetime(2026, 10, 1, 2, 0, tzinfo=UTC) - timedelta(hours=5)
    assert month_keys(tashkent, 1) == ["2026-09"]


async def _key(session, user: uuid.UUID) -> uuid.UUID:
    key = IdempotencyKey(
        user_id=user,
        key=uuid.uuid4().hex,
        request_fingerprint="x",
        expires_at=NOW + timedelta(days=1),
    )
    session.add(key)
    await session.flush()
    return key.id


async def _transfer(
    session,
    *,
    sender: uuid.UUID,
    recipient: uuid.UUID | None,
    amount: int,
    when: datetime,
    status: TransferStatus = TransferStatus.COMPLETED,
    currency: str = "UZS",
) -> None:
    session.add(
        Transfer(
            initiator_user_id=sender,
            recipient_user_id=recipient,
            source_wallet_id=uuid.uuid4(),
            destination_wallet_id=uuid.uuid4(),
            amount_minor=amount,
            currency=currency,
            status=status,
            idempotency_key_id=await _key(session, sender),
            completed_at=when if status == TransferStatus.COMPLETED else None,
            created_at=when,
            updated_at=when,
        )
    )


async def _payment(
    session,
    *,
    payer: uuid.UUID,
    merchant: uuid.UUID,
    amount: int,
    refunded: int,
    status: PaymentStatus,
    when: datetime,
) -> None:
    session.add(
        Payment(
            initiator_user_id=payer,
            source_wallet_id=uuid.uuid4(),
            merchant_id=merchant,
            amount_minor=amount,
            refunded_amount_minor=refunded,
            currency="UZS",
            status=status,
            idempotency_key_id=await _key(session, payer),
            completed_at=when,
            created_at=when,
            updated_at=when,
        )
    )


async def test_counts_what_moved_in_the_month_it_moved(issue_access_token) -> None:
    me, friend = uuid.uuid4(), uuid.uuid4()
    october, september = NOW - timedelta(days=2), datetime(2026, 9, 30, 23, 59, tzinfo=UTC)
    long_ago = datetime(2026, 3, 1, tzinfo=UTC)

    async with db_session.async_session_factory() as session:
        merchant = Merchant(owner_user_id=friend, name="Choyxona")
        session.add(merchant)
        await session.flush()

        await _transfer(session, sender=me, recipient=friend, amount=300_00, when=october)
        await _transfer(session, sender=me, recipient=friend, amount=50_00, when=september)
        await _transfer(session, sender=friend, recipient=me, amount=1_000_00, when=october)
        await _transfer(
            session, sender=friend, recipient=me, amount=7_00, when=october, currency="USD"
        )
        # None of these moved money for me in the period:
        await _transfer(
            session,
            sender=me,
            recipient=friend,
            amount=999_00,
            when=october,
            status=TransferStatus.FAILED,
        )
        await _transfer(
            session,
            sender=me,
            recipient=friend,
            amount=999_00,
            when=october,
            status=TransferStatus.PENDING,
        )
        await _transfer(session, sender=friend, recipient=uuid.uuid4(), amount=999_00, when=october)
        await _transfer(session, sender=me, recipient=friend, amount=999_00, when=long_ago)

        await _payment(
            session,
            payer=me,
            merchant=merchant.id,
            amount=200_00,
            refunded=0,
            status=PaymentStatus.SUCCESS,
            when=october,
        )
        await _payment(
            session,
            payer=me,
            merchant=merchant.id,
            amount=100_00,
            refunded=40_00,
            status=PaymentStatus.PARTIALLY_REFUNDED,
            when=october,
        )
        await _payment(
            session,
            payer=me,
            merchant=merchant.id,
            amount=80_00,
            refunded=80_00,
            status=PaymentStatus.REFUNDED,
            when=october,
        )
        await _payment(
            session,
            payer=me,
            merchant=merchant.id,
            amount=999_00,
            refunded=0,
            status=PaymentStatus.FAILED,
            when=october,
        )
        await session.commit()

        totals = await monthly_totals(session, me, months=3, now=NOW)
        strangers = await monthly_totals(session, uuid.uuid4(), months=3, now=NOW)

    assert list(totals) == ["USD", "UZS"]
    uzs = {entry.month: (entry.in_minor, entry.out_minor) for entry in totals["UZS"]}
    assert uzs == {
        "2026-08": (0, 0),  # a month with nothing still has its place
        "2026-09": (0, 50_00),
        # out: 300 transfer + 200 payment + (100 - 40 refunded) + (80 - 80)
        "2026-10": (1_000_00, 300_00 + 200_00 + 60_00),
    }
    assert [(e.month, e.in_minor, e.out_minor) for e in totals["USD"]][-1] == ("2026-10", 7_00, 0)
    assert strangers == {}


async def test_the_endpoint_returns_every_month_and_totals(issue_access_token) -> None:
    me, friend = uuid.uuid4(), uuid.uuid4()
    async with db_session.async_session_factory() as session:
        await _transfer(session, sender=friend, recipient=me, amount=125_00, when=datetime.now(UTC))
        await _transfer(session, sender=me, recipient=friend, amount=25_00, when=datetime.now(UTC))
        await session.commit()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        headers = {"Authorization": f"Bearer {issue_access_token(me)}"}
        response = await client.get("/api/v1/transactions/stats", headers=headers)
        year = await client.get(
            "/api/v1/transactions/stats", params={"months": 12}, headers=headers
        )
        too_many = await client.get(
            "/api/v1/transactions/stats", params={"months": 25}, headers=headers
        )
        anonymous = await client.get("/api/v1/transactions/stats")

    assert response.status_code == 200
    body = response.json()
    assert len(body["months"]) == 6 and body["months"] == sorted(body["months"])
    [uzs] = body["currencies"]
    assert (uzs["currency"], uzs["total_in_minor"], uzs["total_out_minor"]) == (
        "UZS",
        125_00,
        25_00,
    )
    assert [m["month"] for m in uzs["months"]] == body["months"]
    assert uzs["months"][-1] == {
        "month": body["months"][-1],
        "in_minor": 125_00,
        "out_minor": 25_00,
    }
    assert len(year.json()["months"]) == 12
    assert too_many.status_code == 422 and anonymous.status_code == 401
