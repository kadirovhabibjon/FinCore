"""Narrowing a customer's history (app/services/history.py): by kind,
direction, words and dates - in the listing and in the CSV export."""

import csv
import io
import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import session as db_session
from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.idempotency import IdempotencyKey
from app.domain.merchant import Merchant
from app.domain.payment import Payment, PaymentStatus
from app.domain.transfer import Transfer, TransferStatus

pytestmark = pytest.mark.usefixtures("migrated_database")

_NOW = datetime.now(UTC).replace(hour=12, minute=0, second=0, microsecond=0)


def _days_ago(days: int) -> datetime:
    return _NOW - timedelta(days=days)


async def _history(me: uuid.UUID, other: uuid.UUID) -> dict[str, str]:
    """A small life: money sent, received, paid and exchanged, on
    different days. Returns each operation's reference by a short name."""
    async with db_session.async_session_factory() as session:

        async def key(owner: uuid.UUID) -> uuid.UUID:
            record = IdempotencyKey(
                user_id=owner,
                key=str(uuid.uuid4()),
                request_fingerprint="0" * 64,
                expires_at=_NOW + timedelta(days=1),
            )
            session.add(record)
            await session.flush()
            return record.id

        shop = Merchant(owner_user_id=uuid.uuid4(), name="Chorsu Coffee")
        session.add(shop)
        await session.flush()

        rows = {
            "sent": Transfer(
                initiator_user_id=me, recipient_user_id=other,
                source_wallet_id=uuid.uuid4(), destination_wallet_id=uuid.uuid4(),
                amount_minor=10_000, currency="UZS", status=TransferStatus.COMPLETED,
                description="Lunch 50%_off", sender_name="Me M.", recipient_name="Bobur T.",
                idempotency_key_id=await key(me), created_at=_days_ago(1),
            ),
            "received": Transfer(
                initiator_user_id=other, recipient_user_id=me,
                source_wallet_id=uuid.uuid4(), destination_wallet_id=uuid.uuid4(),
                amount_minor=20_000, currency="UZS", status=TransferStatus.COMPLETED,
                description="Thanks", sender_name="Aziza K.", recipient_name="Me M.",
                idempotency_key_id=await key(other), created_at=_days_ago(3),
            ),
            # Never reached me: it failed on the sender's side.
            "not_mine": Transfer(
                initiator_user_id=other, recipient_user_id=me,
                source_wallet_id=uuid.uuid4(), destination_wallet_id=uuid.uuid4(),
                amount_minor=30_000, currency="UZS", status=TransferStatus.FAILED,
                sender_name="Aziza K.", idempotency_key_id=await key(other),
                created_at=_days_ago(2),
            ),
            "shop": Payment(
                initiator_user_id=me, source_wallet_id=uuid.uuid4(), merchant_id=shop.id,
                amount_minor=5_000, currency="UZS", status=PaymentStatus.SUCCESS,
                merchant_name="Chorsu Coffee", idempotency_key_id=await key(me),
                created_at=_days_ago(5),
            ),
            "phone": Payment(
                initiator_user_id=me, source_wallet_id=uuid.uuid4(), merchant_id=shop.id,
                amount_minor=2_500_000, currency="UZS", status=PaymentStatus.SUCCESS,
                merchant_name="Beeline", description="+998901234567",
                service_code="beeline", service_account="+998901234567",
                idempotency_key_id=await key(me), created_at=_days_ago(8),
            ),
            "exchange": Exchange(
                initiator_user_id=me, source_wallet_id=uuid.uuid4(),
                destination_wallet_id=uuid.uuid4(), source_position_account_id=uuid.uuid4(),
                destination_position_account_id=uuid.uuid4(), source_amount_minor=10_000,
                source_currency="USD", destination_amount_minor=120_000_000,
                destination_currency="UZS", rate=Decimal("12000"),
                status=ExchangeStatus.COMPLETED, idempotency_key_id=await key(me),
                created_at=_days_ago(10),
            ),
        }
        session.add_all(rows.values())
        await session.commit()
        return {name: row.reference for name, row in rows.items()}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app_under_test()), base_url="http://test")


def app_under_test():  # imported late so the fixtures have patched the settings
    from app.main import app

    return app


async def _listed(client: AsyncClient, token: str, **params: str) -> list[str]:
    response = await client.get(
        "/api/v1/transactions", params=params, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200, response.text
    return [item["reference"] for item in response.json()]


async def test_history_narrows_by_kind_direction_words_and_dates(issue_access_token) -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    ref = await _history(me, other)
    token = issue_access_token(me)
    everything = [ref[name] for name in ("sent", "received", "shop", "phone", "exchange")]

    async with _client() as client:
        assert await _listed(client, token) == everything

        # kind
        assert await _listed(client, token, type="TRANSFER") == [ref["sent"], ref["received"]]
        assert await _listed(client, token, type="PAYMENT") == [ref["shop"], ref["phone"]]
        assert await _listed(client, token, type="EXCHANGE") == [ref["exchange"]]

        # direction
        assert await _listed(client, token, direction="IN") == [ref["received"]]
        assert await _listed(client, token, direction="OUT") == [
            ref["sent"],
            ref["shop"],
            ref["phone"],
        ]
        assert await _listed(client, token, direction="SELF") == [ref["exchange"]]
        assert await _listed(client, token, type="PAYMENT", direction="IN") == []
        assert await _listed(client, token, type="TRANSFER", direction="OUT") == [ref["sent"]]

        # words: the other side's name, a note, a merchant, an account, a reference
        assert await _listed(client, token, q="bobur") == [ref["sent"]]
        assert await _listed(client, token, q="AZIZA") == [ref["received"]]
        assert await _listed(client, token, q="  coffee ") == [ref["shop"]]
        assert await _listed(client, token, q="901234567") == [ref["phone"]]
        assert await _listed(client, token, q="beeline") == [ref["phone"]]
        assert await _listed(client, token, q=ref["exchange"][-6:].lower()) == [ref["exchange"]]
        assert await _listed(client, token, q="lunch") == [ref["sent"]]
        # My own name is on every transfer of mine; it is not what I search by.
        assert await _listed(client, token, q="Me M.") == []
        assert await _listed(client, token, q="nothing like this") == []

        # dates, both days included
        day = lambda days: str(_days_ago(days).date())  # noqa: E731
        assert await _listed(client, token, date_from=day(3)) == [ref["sent"], ref["received"]]
        assert await _listed(client, token, date_to=day(8)) == [ref["phone"], ref["exchange"]]
        assert await _listed(client, token, date_from=day(5), date_to=day(3)) == [
            ref["received"],
            ref["shop"],
        ]
        assert await _listed(client, token, date_from=day(5), date_to=day(5)) == [ref["shop"]]

        # together, and paged within what matched
        assert await _listed(client, token, direction="OUT", q="o", date_from=day(6)) == [
            ref["sent"],
            ref["shop"],
        ]
        assert await _listed(client, token, direction="OUT", limit="1", offset="1") == [ref["shop"]]


async def test_what_the_customer_types_is_text_not_a_pattern(issue_access_token) -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    ref = await _history(me, other)
    token = issue_access_token(me)

    async with _client() as client:
        assert await _listed(client, token, q="50%_off") == [ref["sent"]]
        # As patterns these would match everything.
        assert await _listed(client, token, q="%") == [ref["sent"]]
        assert await _listed(client, token, q="_") == [ref["sent"]]
        assert await _listed(client, token, q="\\") == []
        assert await _listed(client, token, q="'; drop table transfers; --") == []
        assert len(await _listed(client, token)) == 5


async def test_a_filter_never_shows_what_was_not_the_callers(issue_access_token) -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    ref = await _history(me, other)

    async with _client() as client:
        mine = issue_access_token(me)
        theirs = issue_access_token(other)
        # The transfer that failed before reaching me, however I ask for it.
        for params in ({}, {"direction": "IN"}, {"q": "Aziza"}, {"type": "TRANSFER"}):
            assert ref["not_mine"] not in await _listed(client, mine, **params)
        # The other person sees their side, and none of my payments.
        assert await _listed(client, theirs, q="coffee") == []
        assert await _listed(client, theirs, direction="IN") == [ref["sent"]]
        assert await _listed(client, theirs, direction="OUT") == [ref["not_mine"], ref["received"]]


@pytest.mark.parametrize(
    "params",
    [{"type": "LOAN"}, {"direction": "UP"}, {"date_from": "yesterday"}, {"q": "x" * 65}],
)
async def test_a_malformed_filter_is_refused(issue_access_token, params: dict) -> None:
    async with _client() as client:
        response = await client.get(
            "/api/v1/transactions",
            params=params,
            headers={"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"},
        )

    assert response.status_code == 422


async def test_the_csv_holds_what_the_filter_lists(issue_access_token) -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    ref = await _history(me, other)
    headers = {"Authorization": f"Bearer {issue_access_token(me)}"}

    async with _client() as client:
        whole = await client.get("/api/v1/transactions/export.csv", headers=headers)
        paid = await client.get(
            "/api/v1/transactions/export.csv", params={"type": "PAYMENT"}, headers=headers
        )

    def references(response) -> list[str]:  # type: ignore[no-untyped-def]
        text = response.content.decode("utf-8-sig")
        return [row["reference"] for row in csv.DictReader(io.StringIO(text))]

    assert len(references(whole)) == 5
    assert references(paid) == [ref["shop"], ref["phone"]]


async def test_spending_is_split_by_what_it_paid_for(issue_access_token) -> None:
    me, other = uuid.uuid4(), uuid.uuid4()
    await _history(me, other)
    headers = {"Authorization": f"Bearer {issue_access_token(me)}"}

    async with _client() as client:
        async with db_session.async_session_factory() as session:
            shop = Merchant(owner_user_id=uuid.uuid4(), name="Bookshop")
            session.add(shop)
            await session.flush()
            for amount, refunded, status in (
                (40_000, 10_000, PaymentStatus.PARTIALLY_REFUNDED),  # 300.00 spent
                (7_000, 7_000, PaymentStatus.REFUNDED),  # nothing spent
                (9_000, 0, PaymentStatus.FAILED),  # never paid
            ):
                key = IdempotencyKey(
                    user_id=me, key=str(uuid.uuid4()), request_fingerprint="0" * 64,
                    expires_at=_NOW + timedelta(days=1),
                )
                session.add(key)
                await session.flush()
                session.add(
                    Payment(
                        initiator_user_id=me, source_wallet_id=uuid.uuid4(), merchant_id=shop.id,
                        amount_minor=amount, refunded_amount_minor=refunded, currency="UZS",
                        status=status, merchant_name="Bookshop", idempotency_key_id=key.id,
                        created_at=_days_ago(1), completed_at=_days_ago(1),
                    )
                )
            await session.commit()

        year = await client.get(
            "/api/v1/transactions/stats/categories", params={"months": 12}, headers=headers
        )
        out_total = await client.get(
            "/api/v1/transactions/stats", params={"months": 12}, headers=headers
        )
        other_person = await client.get(
            "/api/v1/transactions/stats/categories",
            params={"months": 12},
            headers={"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"},
        )
        anonymous = await client.get("/api/v1/transactions/stats/categories")
        too_long = await client.get(
            "/api/v1/transactions/stats/categories", params={"months": 25}, headers=headers
        )

    assert anonymous.status_code == 401 and too_long.status_code == 422
    assert other_person.json()["currencies"] == []
    body = year.json()
    assert len(body["months"]) == 12
    # The exchange (my own money changing currency) spent nothing: no USD.
    assert [entry["currency"] for entry in body["currencies"]] == ["UZS"]
    uzs = body["currencies"][0]
    assert uzs["categories"] == [
        {"category": "MOBILE", "amount_minor": 2_500_000, "count": 1},
        # The coffee, and the book net of its partial refund; not the
        # one refunded in full, nor the one that failed.
        {"category": "SHOPS", "amount_minor": 5_000 + 30_000, "count": 2},
        {"category": "TRANSFERS", "amount_minor": 10_000, "count": 1},
    ]
    assert uzs["total_minor"] == 2_545_000
    # The same money the monthly statistics call "out".
    monthly = next(c for c in out_total.json()["currencies"] if c["currency"] == "UZS")
    assert monthly["total_out_minor"] == uzs["total_minor"]
