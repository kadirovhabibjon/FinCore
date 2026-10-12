"""Scheduled payments (app/services/autopay.py): the schedule itself,
the API around it, and a run - made at most once, as an ordinary
operation."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fincore_common import generate_card_number
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.api.v1 import scheduled_payments as scheduled_api
from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.domain.payment import Payment
from app.domain.scheduled_payment import ScheduledPayment, ScheduleInterval
from app.domain.transfer import Transfer
from app.main import app
from app.services import autopay, fraud, identity, ledger
from app.services.autopay import next_run

pytestmark = pytest.mark.usefixtures("migrated_database")

_CARD = generate_card_number()


class World:
    """The other services, as far as a scheduled payment needs them."""

    def __init__(self, owner: uuid.UUID) -> None:
        self.owner = owner
        self.wallet = uuid.uuid4()
        self.wallet_currency = "UZS"
        self.wallet_owner: uuid.UUID | None = owner
        self.recipient = uuid.uuid4()
        self.recipient_wallet = uuid.uuid4()
        self.card_known = True
        self.ledger_down = False
        self.posting_status = 201
        self.postings: list[dict] = []
        self.holds: list[dict] = []


def _ledger_app(world: World) -> FastAPI:
    fake = FastAPI()

    def wallet(wallet_id: str, owner: uuid.UUID, card: str = "9955000000000006") -> dict:
        return {
            "id": wallet_id,
            "owner_user_id": str(owner),
            "card_number": card,
            "currency": world.wallet_currency,
            "status": "ACTIVE",
            "created_at": "2026-01-01T00:00:00Z",
            "balance_minor": 0,
            "held_minor": 0,
            "name": None,
            "is_primary": True,
            "blocked": False,
        }

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _public(wallet_id: str) -> JSONResponse:
        if wallet_id != str(world.wallet):
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
        return JSONResponse(wallet(wallet_id, world.owner))

    @fake.get("/internal/v1/accounts/wallets/{wallet_id}")
    async def _owner(wallet_id: str) -> JSONResponse:
        if world.ledger_down:
            return JSONResponse({"title": "x", "status": 503}, status_code=503)
        if wallet_id == str(world.wallet) and world.wallet_owner is not None:
            return JSONResponse(wallet(wallet_id, world.wallet_owner))
        if wallet_id == str(world.recipient_wallet):
            return JSONResponse(wallet(wallet_id, world.recipient, _CARD))
        return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)

    @fake.get("/internal/v1/accounts/wallet-by-card")
    async def _by_card(card_number: str) -> JSONResponse:
        if world.ledger_down:
            return JSONResponse({"title": "x", "status": 503}, status_code=503)
        if not world.card_known or card_number != _CARD:
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
        return JSONResponse(wallet(str(world.recipient_wallet), world.recipient, _CARD))

    @fake.post("/internal/v1/postings")
    async def _posting(request: Request) -> JSONResponse:
        payload = await request.json()
        world.postings.append(payload)
        if world.posting_status >= 400:
            return JSONResponse(
                {"title": "Insufficient Funds", "status": world.posting_status},
                status_code=world.posting_status,
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
            status_code=201,
        )

    @fake.post("/internal/v1/holds")
    async def _hold(request: Request) -> JSONResponse:
        payload = await request.json()
        world.holds.append(payload)
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
    async def _capture(hold_id: str, request: Request) -> JSONResponse:
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


def _identity_app() -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/users/{user_id}")
    async def _user(user_id: str) -> JSONResponse:
        return JSONResponse(
            {"id": user_id, "first_name": "Bobur", "last_name": "Tursunov", "status": "ACTIVE"}
        )

    return fake


def _fraud_app() -> FastAPI:
    fake = FastAPI()

    @fake.post("/internal/v1/risk-checks")
    async def _check() -> JSONResponse:
        return JSONResponse({"decision": "ALLOW", "score": 1})

    return fake


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    made = World(uuid.uuid4())
    token = settings.internal_service_token
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger", internal_token=token, timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_ledger_app(made)),
        ),
    )
    monkeypatch.setattr(
        identity,
        "identity_client",
        identity.IdentityClient(
            base_url="http://identity", internal_token=token, timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_identity_app()),
        ),
    )
    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud", internal_token=token, timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=httpx.ASGITransport(app=_fraud_app()),
        ),
    )
    return made


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _service(world: World, **overrides: object) -> dict:
    return {
        "name": "Home internet",
        "kind": "SERVICE",
        "service_code": "uzonline",
        "account": "aziza_01",
        "source_wallet_id": str(world.wallet),
        "amount": "150000",
        "interval": "MONTHLY",
        "day": 5,
        **overrides,
    }


def _transfer(world: World, **overrides: object) -> dict:
    return {
        "name": "Rent",
        "kind": "TRANSFER",
        "card_number": _CARD,
        "source_wallet_id": str(world.wallet),
        "amount": "2500.00",
        "interval": "WEEKLY",
        "day": 1,
        **overrides,
    }


async def _create(client: AsyncClient, headers: dict, payload: dict) -> dict:
    response = await client.post("/api/v1/scheduled-payments", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()


async def _make_due(scheduled_id: str, *, ago: timedelta = timedelta(minutes=1)) -> datetime:
    due = datetime.now(UTC) - ago
    async with db_session.async_session_factory() as session:
        await session.execute(
            update(ScheduledPayment)
            .where(ScheduledPayment.id == uuid.UUID(scheduled_id))
            .values(next_run_at=due)
        )
        await session.commit()
    return due


async def _run() -> int:
    async with db_session.async_session_factory() as session:
        return await autopay.run_due(session)


async def _stored(scheduled_id: str) -> ScheduledPayment:
    async with db_session.async_session_factory() as session:
        stored = await session.get(ScheduledPayment, uuid.UUID(scheduled_id))
        assert stored is not None
        return stored


# --- the schedule ----------------------------------------------------------


def test_the_next_run_is_the_first_such_day_strictly_after_now() -> None:
    hour = settings.autopay_hour_utc
    wednesday = datetime(2026, 10, 14, 12, 0, tzinfo=UTC)

    # Weekly: ISO weekdays, 1 is Monday.
    assert next_run(ScheduleInterval.WEEKLY, 5, after=wednesday) == datetime(
        2026, 10, 16, hour, tzinfo=UTC
    )
    assert next_run(ScheduleInterval.WEEKLY, 1, after=wednesday) == datetime(
        2026, 10, 19, hour, tzinfo=UTC
    )
    # Today's hour has passed: next week, not an hour ago.
    assert next_run(ScheduleInterval.WEEKLY, 3, after=wednesday) == datetime(
        2026, 10, 21, hour, tzinfo=UTC
    )
    # Earlier the same day: still today.
    early = datetime(2026, 10, 14, hour - 1, 59, tzinfo=UTC)
    assert next_run(ScheduleInterval.WEEKLY, 3, after=early) == datetime(
        2026, 10, 14, hour, tzinfo=UTC
    )
    # Exactly at the hour: that run is this one, the next is a week on.
    at = datetime(2026, 10, 14, hour, tzinfo=UTC)
    assert next_run(ScheduleInterval.WEEKLY, 3, after=at) == at + timedelta(days=7)

    # Monthly, across a month and a year end.
    assert next_run(ScheduleInterval.MONTHLY, 20, after=wednesday) == datetime(
        2026, 10, 20, hour, tzinfo=UTC
    )
    assert next_run(ScheduleInterval.MONTHLY, 5, after=wednesday) == datetime(
        2026, 11, 5, hour, tzinfo=UTC
    )
    assert next_run(
        ScheduleInterval.MONTHLY, 28, after=datetime(2026, 12, 29, tzinfo=UTC)
    ) == datetime(2027, 1, 28, hour, tzinfo=UTC)
    # February has a 28th every year: the reason days stop there.
    assert next_run(
        ScheduleInterval.MONTHLY, 28, after=datetime(2027, 2, 1, tzinfo=UTC)
    ) == datetime(2027, 2, 28, hour, tzinfo=UTC)


# --- the API ---------------------------------------------------------------


async def test_a_payment_is_scheduled_checked_as_the_payment_would_be(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}

    async with _client() as client:
        internet = await _create(client, headers, _service(world))
        rent = await _create(client, headers, _transfer(world))
        listed = await client.get("/api/v1/scheduled-payments", headers=headers)
        anonymous = await client.get("/api/v1/scheduled-payments")

    assert internet["service_account"] == "aziza_01" and internet["currency"] == "UZS"
    assert internet["amount_minor"] == 15_000_000
    assert (internet["interval"], internet["day"], internet["status"]) == ("MONTHLY", 5, "ACTIVE")
    assert internet["last_run_at"] is None and internet["last_status"] is None
    next_at = datetime.fromisoformat(internet["next_run_at"])
    assert next_at > datetime.now(UTC) and (next_at.day, next_at.hour) == (5, 4)
    assert (rent["card_number"], rent["recipient_name"]) == (_CARD, "Bobur T.")
    assert rent["amount_minor"] == 250_000
    # Soonest first.
    assert [item["id"] for item in listed.json()] == sorted(
        [internet["id"], rent["id"]],
        key=lambda i: internet["next_run_at"] if i == internet["id"] else rent["next_run_at"],
    )
    assert anonymous.status_code == 401
    # Scheduling pays nothing.
    assert world.postings == [] and world.holds == []


async def test_what_could_not_be_paid_is_not_scheduled(world: World, issue_access_token) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    world.card_known = True
    cases = [
        (_service(world, day=29), 422, "Invalid Schedule"),
        (_service(world, day=0), 422, "Invalid Schedule"),
        (_transfer(world, day=8), 422, "Invalid Schedule"),
        (_service(world, source_wallet_id=str(uuid.uuid4())), 404, "Wallet Not Found"),
        (_service(world, amount="0"), 422, "Invalid Amount"),
        (_service(world, amount="500"), 422, "Amount Out Of Range"),
        (_service(world, service_code="moon-cable"), 404, "Service Not Found"),
        (_service(world, account="x"), 422, "Invalid Service Account"),
        (_service(world, card_number=_CARD), 422, "Invalid Template"),
        (_transfer(world, card_number="1234567890123456"), 422, "Invalid Card Number"),
        (_transfer(world, card_number=generate_card_number()), 404, "Recipient Not Found"),
        (_transfer(world, service_code="beeline"), 422, "Invalid Template"),
    ]

    async with _client() as client:
        for payload, status_code, title in cases:
            response = await client.post(
                "/api/v1/scheduled-payments", json=payload, headers=headers
            )
            assert (response.status_code, response.json()["title"]) == (status_code, title), payload
        world.wallet_currency = "USD"
        wrong_currency = await client.post(
            "/api/v1/scheduled-payments", json=_service(world, amount="100"), headers=headers
        )
        listed = await client.get("/api/v1/scheduled-payments", headers=headers)

    assert wrong_currency.status_code == 422
    assert wrong_currency.json()["title"] == "Currency Mismatch"
    assert listed.json() == []


async def test_scheduled_payments_are_the_owners_alone_and_limited(
    world: World, issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    theirs = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    monkeypatch.setattr(scheduled_api, "MAX_SCHEDULED", 2)

    async with _client() as client:
        first = await _create(client, mine, _service(world))
        await _create(client, mine, _service(world, name="Second"))
        third = await client.post(
            "/api/v1/scheduled-payments", json=_service(world, name="Third"), headers=mine
        )
        url = f"/api/v1/scheduled-payments/{first['id']}"
        seen = await client.get("/api/v1/scheduled-payments", headers=theirs)
        paused = await client.patch(url, json={"status": "PAUSED"}, headers=theirs)
        deleted = await client.delete(url, headers=theirs)
        mine_deleted = await client.delete(url, headers=mine)
        again = await client.delete(url, headers=mine)
        left = await client.get("/api/v1/scheduled-payments", headers=mine)

    assert third.status_code == 409 and third.json()["title"] == "Too Many Scheduled Payments"
    assert seen.json() == []
    assert paused.status_code == deleted.status_code == again.status_code == 404
    assert paused.json()["title"] == "Scheduled Payment Not Found"
    assert mine_deleted.status_code == 204
    assert [item["name"] for item in left.json()] == ["Second"]


# --- a run -----------------------------------------------------------------


async def test_a_due_service_payment_is_made_as_an_ordinary_payment(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _service(world))
        assert await _run() == 0  # not due yet
        await _make_due(scheduled["id"])
        assert await _run() == 1
        history = (await client.get("/api/v1/transactions", headers=headers)).json()
        shown = (await client.get("/api/v1/scheduled-payments", headers=headers)).json()[0]

    assert len(history) == 1
    assert (history[0]["type"], history[0]["status"]) == ("PAYMENT", "SUCCESS")
    assert history[0]["amount_minor"] == 15_000_000 and history[0]["description"] == "aziza_01"
    assert shown["last_status"] == "SUCCESS" and shown["last_error"] is None
    assert shown["last_operation_id"] == history[0]["id"]
    assert datetime.fromisoformat(shown["next_run_at"]) > datetime.now(UTC)
    assert len(world.holds) == 1 and world.holds[0]["amount_minor"] == 15_000_000

    async with db_session.async_session_factory() as session:
        payment = await session.get(Payment, uuid.UUID(history[0]["id"]))
        events = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == history[0]["id"])
            )
        ).scalars().all()
    assert payment is not None and payment.service_code == "uzonline"
    # The customer is told like for any payment.
    assert [event.event_type for event in events] == ["payment.completed"]


async def test_a_due_transfer_goes_to_whoever_holds_the_card_now(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _transfer(world))
        await _make_due(scheduled["id"])
        assert await _run() == 1
        history = (await client.get("/api/v1/transactions", headers=headers)).json()

    assert (history[0]["type"], history[0]["status"]) == ("TRANSFER", "COMPLETED")
    assert history[0]["counterparty_name"] == "Bobur T."
    assert history[0]["description"] == "Rent"
    entries = world.postings[0]["entries"]
    assert {entry["account_id"] for entry in entries} == {
        str(world.wallet),
        str(world.recipient_wallet),
    }
    async with db_session.async_session_factory() as session:
        transfer = await session.get(Transfer, uuid.UUID(history[0]["id"]))
    assert transfer is not None and transfer.recipient_user_id == world.recipient


async def test_a_run_is_made_once_however_many_workers_see_it(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _service(world))
        await _make_due(scheduled["id"])
        made = await asyncio.gather(*(_run() for _ in range(6)))
        again = await _run()
        history = (await client.get("/api/v1/transactions", headers=headers)).json()

    assert sum(made) == 1 and again == 0
    assert len(history) == 1 and len(world.holds) == 1


async def test_a_run_the_ledger_refuses_is_a_failed_operation_and_the_schedule_goes_on(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    world.posting_status = 409
    async with _client() as client:
        scheduled = await _create(client, headers, _transfer(world))
        await _make_due(scheduled["id"])
        assert await _run() == 1
        history = (await client.get("/api/v1/transactions", headers=headers)).json()

    stored = await _stored(scheduled["id"])
    assert (history[0]["status"], stored.last_status) == ("FAILED", "FAILED")
    assert stored.last_error == "Insufficient Funds"
    # Not retried until its next occurrence; still active for that one.
    assert stored.status.value == "ACTIVE" and stored.next_run_at > datetime.now(UTC)
    assert await _run() == 0


async def test_while_a_service_cannot_answer_nothing_is_claimed(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _transfer(world))
        due = await _make_due(scheduled["id"])
        world.ledger_down = True
        assert await _run() == 0
        waiting = await _stored(scheduled["id"])
        world.ledger_down = False
        assert await _run() == 1
        history = (await client.get("/api/v1/transactions", headers=headers)).json()

    # Still due, untouched, while the ledger was away...
    assert waiting.next_run_at == due and waiting.last_status is None
    # ...and made once it was back.
    assert [item["status"] for item in history] == ["COMPLETED"]


@pytest.mark.parametrize(
    ("break_it", "reason"),
    [
        (lambda world: setattr(world, "wallet_owner", None), "Wallet Not Found"),
        (lambda world: setattr(world, "wallet_owner", uuid.uuid4()), "Wallet Not Found"),
        (lambda world: setattr(world, "card_known", False), "Recipient Not Found"),
    ],
    ids=["wallet gone", "wallet someone else's", "recipient's card gone"],
)
async def test_a_run_that_cannot_even_start_says_why_and_moves_nothing(
    world: World, issue_access_token, break_it, reason: str
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _transfer(world))
        await _make_due(scheduled["id"])
        break_it(world)
        assert await _run() == 1
        history = (await client.get("/api/v1/transactions", headers=headers)).json()

    stored = await _stored(scheduled["id"])
    assert (stored.last_status, stored.last_error) == ("NOT_RUN", reason)
    assert stored.last_operation_id is None and stored.next_run_at > datetime.now(UTC)
    assert history == [] and world.postings == []


async def test_a_paused_schedule_does_not_run_and_resumes_from_now(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _service(world))
        url = f"/api/v1/scheduled-payments/{scheduled['id']}"
        paused = await client.patch(url, json={"status": "PAUSED"}, headers=headers)
        await _make_due(scheduled["id"], ago=timedelta(days=40))
        ran_while_paused = await _run()
        resumed = await client.patch(url, json={"status": "ACTIVE"}, headers=headers)
        ran_after = await _run()

    assert paused.json()["status"] == "PAUSED"
    assert ran_while_paused == 0
    # The runs missed while paused are not made up for.
    assert resumed.json()["status"] == "ACTIVE"
    assert datetime.fromisoformat(resumed.json()["next_run_at"]) > datetime.now(UTC)
    assert ran_after == 0 and world.holds == []


async def test_a_schedule_long_overdue_runs_once_not_once_per_missed_day(
    world: World, issue_access_token
) -> None:
    headers = {"Authorization": f"Bearer {issue_access_token(world.owner)}"}
    async with _client() as client:
        scheduled = await _create(client, headers, _transfer(world))
        await _make_due(scheduled["id"], ago=timedelta(days=30))
        first, second = await _run(), await _run()

    stored = await _stored(scheduled["id"])
    assert (first, second) == (1, 0)
    assert len(world.postings) == 1
    assert stored.next_run_at > datetime.now(UTC)
