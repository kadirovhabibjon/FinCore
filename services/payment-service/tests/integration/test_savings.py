"""Savings goals (app/services/savings.py): money set aside and taken
back, and the goal's own figure staying true to the ledger through
refusals, races and a ledger that does not answer."""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.api.v1 import savings as savings_api
from app.core.config import settings
from app.db import session as db_session
from app.domain.savings import SavingsGoal, SavingsMovement
from app.main import app
from app.services import ledger, savings

pytestmark = pytest.mark.usefixtures("migrated_database")


class Book:
    """A ledger that remembers: enough of one to see where money is."""

    def __init__(self) -> None:
        self.wallet = uuid.uuid4()
        self.pool = uuid.uuid4()
        self.currency = "UZS"
        self.balances = {self.wallet: 1_000_000, self.pool: 0}
        self.posted: dict[str, dict] = {}
        self.calls = 0
        # What the next posting does: "ok", "refuse", "silent" (the
        # posting is made but the answer is lost), "down" (nothing happens).
        self.mode = "ok"
        self.pool_known = True

    def apply(self, payload: dict) -> None:
        for entry in payload["entries"]:
            account = uuid.UUID(entry["account_id"])
            sign = 1 if entry["direction"] == "CREDIT" else -1
            self.balances[account] += sign * entry["amount_minor"]


def _ledger_app(book: Book) -> FastAPI:
    fake = FastAPI()

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _wallet(wallet_id: str) -> JSONResponse:
        if wallet_id != str(book.wallet):
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
        return JSONResponse(
            {
                "id": wallet_id,
                "card_number": "9955000000000006",
                "currency": book.currency,
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "balance_minor": book.balances[book.wallet],
                "held_minor": 0,
                "name": None,
                "is_primary": True,
                "blocked": False,
            }
        )

    @fake.get("/internal/v1/accounts/system")
    async def _system(kind: str, currency: str) -> JSONResponse:
        if not book.pool_known or kind != "SAVINGS":
            return JSONResponse({"title": "Unknown Account", "status": 404}, status_code=404)
        return JSONResponse({"id": str(book.pool), "kind": kind, "currency": currency})

    @fake.post("/internal/v1/postings")
    async def _posting(request: Request) -> JSONResponse:
        payload = await request.json()
        book.calls += 1
        answer = {
            "id": str(uuid.uuid4()),
            "source_service": payload["source_service"],
            "source_id": payload["source_id"],
            "type": payload["type"],
            "currency": payload["currency"],
            "created_at": "2026-01-01T00:00:00Z",
        }
        if payload["source_id"] in book.posted:  # idempotent, like the real one
            return JSONResponse(book.posted[payload["source_id"]], status_code=200)
        if book.mode == "down":
            return JSONResponse({"title": "x", "status": 503}, status_code=503)
        if book.mode == "refuse":
            return JSONResponse({"title": "Wallet Blocked", "status": 409}, status_code=409)
        debit = next(e for e in payload["entries"] if e["direction"] == "DEBIT")
        if book.balances[uuid.UUID(debit["account_id"])] < debit["amount_minor"]:
            return JSONResponse({"title": "Insufficient Funds", "status": 409}, status_code=409)
        book.apply(payload)
        book.posted[payload["source_id"]] = answer
        if book.mode == "silent":
            return JSONResponse({"title": "x", "status": 500}, status_code=500)
        return JSONResponse(answer, status_code=201)

    return fake


@pytest.fixture
def book(monkeypatch: pytest.MonkeyPatch) -> Book:
    made = Book()
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_ledger_app(made)),
        ),
    )
    return made


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _goal(client: AsyncClient, token: str, target: str = "5000.00") -> dict:
    response = await client.post(
        "/api/v1/savings-goals",
        json={"name": "  New   phone ", "currency": "UZS", "target": target},
        headers=_auth(token),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _move(
    client: AsyncClient,
    token: str,
    goal_id: str,
    book: Book,
    how: str,
    amount: str,
    key: str | None = None,
) -> dict:
    response = await client.post(
        f"/api/v1/savings-goals/{goal_id}/{how}",
        json={"wallet_id": str(book.wallet), "amount": amount},
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )
    return {"status_code": response.status_code, **response.json()}


async def _saved(client: AsyncClient, token: str) -> int:
    goals = (await client.get("/api/v1/savings-goals", headers=_auth(token))).json()
    return goals[0]["saved_minor"]


async def _recover() -> list[SavingsMovement]:
    async with db_session.async_session_factory() as session:
        await session.execute(
            update(SavingsMovement).values(updated_at=datetime.now(UTC) - timedelta(minutes=5))
        )
        await session.commit()
        return await savings.resolve_stuck(session, stuck_after_seconds=60)


async def test_money_set_aside_leaves_the_wallet_for_the_pool_and_comes_back(
    book: Book, issue_access_token
) -> None:
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        put_in = await _move(client, token, goal["id"], book, "deposit", "300.00")
        after_in = (await _saved(client, token), dict(book.balances))
        taken = await _move(client, token, goal["id"], book, "withdraw", "120.50")
        after_out = (await _saved(client, token), dict(book.balances))
        movements = await client.get(
            f"/api/v1/savings-goals/{goal['id']}/movements", headers=_auth(token)
        )

    assert goal | {"id": "", "created_at": ""} == {
        "id": "",
        "name": "New phone",
        "currency": "UZS",
        "target_minor": 500_000,
        "saved_minor": 0,
        "created_at": "",
    }
    assert (put_in["status_code"], put_in["status"], put_in["direction"]) == (
        201,
        "COMPLETED",
        "DEPOSIT",
    )
    assert put_in["reference"].startswith("SAV-") and put_in["completed_at"]
    assert after_in == (30_000, {book.wallet: 970_000, book.pool: 30_000})
    assert taken["status"] == "COMPLETED"
    assert after_out == (17_950, {book.wallet: 982_050, book.pool: 17_950})
    # Newest first; what the goal says is what the pool holds.
    assert [m["direction"] for m in movements.json()] == ["WITHDRAW", "DEPOSIT"]


async def test_a_goal_gives_back_only_what_it_holds(book: Book, issue_access_token) -> None:
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        await _move(client, token, goal["id"], book, "deposit", "100.00")
        calls = book.calls
        too_much = await _move(client, token, goal["id"], book, "withdraw", "100.01")
        exactly = await _move(client, token, goal["id"], book, "withdraw", "100.00")
        saved = await _saved(client, token)

    assert too_much["status_code"] == 201
    assert (too_much["status"], too_much["failure_reason"]) == ("FAILED", "Insufficient Savings")
    # Refused here, before the ledger was ever asked.
    assert book.calls == calls + 1
    assert exactly["status"] == "COMPLETED" and saved == 0
    assert book.balances == {book.wallet: 1_000_000, book.pool: 0}


async def test_withdrawals_racing_for_the_last_of_it_cannot_all_win(
    book: Book, issue_access_token
) -> None:
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        await _move(client, token, goal["id"], book, "deposit", "100.00")
        results = await asyncio.gather(
            *(_move(client, token, goal["id"], book, "withdraw", "60.00") for _ in range(6))
        )
        saved = await _saved(client, token)

    assert [r["status"] for r in results].count("COMPLETED") == 1
    assert [r["failure_reason"] for r in results].count("Insufficient Savings") == 5
    assert saved == 4_000
    assert book.balances[book.pool] == 4_000 and book.balances[book.wallet] == 996_000


async def test_what_the_ledger_refuses_changes_nothing(book: Book, issue_access_token) -> None:
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        beyond = await _move(client, token, goal["id"], book, "deposit", "20000.00")
        await _move(client, token, goal["id"], book, "deposit", "100.00")
        book.mode = "refuse"
        blocked_in = await _move(client, token, goal["id"], book, "deposit", "50.00")
        blocked_out = await _move(client, token, goal["id"], book, "withdraw", "40.00")
        saved = await _saved(client, token)

    # More than the wallet has.
    assert (beyond["status"], beyond["failure_reason"]) == ("FAILED", "Insufficient Funds")
    assert (blocked_in["status"], blocked_in["failure_reason"]) == ("FAILED", "Wallet Blocked")
    assert blocked_out["status"] == "FAILED"
    # The withdrawal's amount, taken off the goal when it began, is back.
    assert saved == 10_000
    assert book.balances == {book.wallet: 990_000, book.pool: 10_000}


@pytest.mark.parametrize("mode", ["silent", "down"])
async def test_a_ledger_that_does_not_answer_loses_nothing(
    book: Book, issue_access_token, mode: str
) -> None:
    """`silent`: the posting was made, its answer lost. `down`: nothing
    was made. From here they look the same - so neither is called a
    failure, and asking again settles each as what it was."""
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        await _move(client, token, goal["id"], book, "deposit", "500.00")

        book.mode = mode
        put_in = await _move(client, token, goal["id"], book, "deposit", "100.00")
        taken = await _move(client, token, goal["id"], book, "withdraw", "200.00")
        while_unknown = await _saved(client, token)
        too_much_meanwhile = await _move(client, token, goal["id"], book, "withdraw", "300.01")

        book.mode = "ok"
        first = await _recover()
        second = await _recover()  # nothing left; nothing is counted twice
        settled = await _saved(client, token)
        movements = (
            await client.get(f"/api/v1/savings-goals/{goal['id']}/movements", headers=_auth(token))
        ).json()

    assert put_in["status"] == taken["status"] == "PENDING"
    # Not yet counted in; already counted out.
    assert while_unknown == 50_000 - 20_000
    assert too_much_meanwhile["failure_reason"] == "Insufficient Savings"
    assert len(first) == 2 and second == []
    assert settled == 50_000 + 10_000 - 20_000
    assert book.balances == {book.wallet: 960_000, book.pool: 40_000}
    statuses = {m["direction"] + ":" + m["status"] for m in movements}
    assert {"DEPOSIT:COMPLETED", "WITHDRAW:COMPLETED", "WITHDRAW:FAILED"} <= statuses


async def test_a_retry_with_the_same_key_moves_the_money_once(
    book: Book, issue_access_token
) -> None:
    token, key = issue_access_token(uuid.uuid4()), str(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        first = await _move(client, token, goal["id"], book, "deposit", "300.00", key)
        again = await _move(client, token, goal["id"], book, "deposit", "300.00", key)
        # The withdrawal that empties the goal, replayed once it is empty.
        out_key = str(uuid.uuid4())
        out = await _move(client, token, goal["id"], book, "withdraw", "300.00", out_key)
        out_again = await _move(client, token, goal["id"], book, "withdraw", "300.00", out_key)
        saved = await _saved(client, token)

    assert again == first and out_again == out
    assert out["status"] == "COMPLETED" and saved == 0
    assert book.balances == {book.wallet: 1_000_000, book.pool: 0}


async def test_only_an_empty_goal_with_nothing_on_its_way_can_be_closed(
    book: Book, issue_access_token
) -> None:
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        url = f"/api/v1/savings-goals/{goal['id']}"
        await _move(client, token, goal["id"], book, "deposit", "100.00")
        with_money = await client.delete(url, headers=_auth(token))

        book.mode = "down"
        leaving = await _move(client, token, goal["id"], book, "withdraw", "100.00")
        # Empty by its own figure, but the money hasn't left yet.
        on_its_way = await client.delete(url, headers=_auth(token))
        book.mode = "ok"
        await _recover()

        closed = await client.delete(url, headers=_auth(token))
        again = await client.delete(url, headers=_auth(token))
        listed = await client.get("/api/v1/savings-goals", headers=_auth(token))
        into_closed = await _move(client, token, goal["id"], book, "deposit", "10.00")

    assert with_money.status_code == 409 and with_money.json()["title"] == "Goal Not Empty"
    assert leaving["status"] == "PENDING" and on_its_way.status_code == 409
    assert closed.status_code == 204 and again.status_code == 404
    assert listed.json() == []
    assert into_closed["status_code"] == 404
    assert book.balances == {book.wallet: 1_000_000, book.pool: 0}


async def test_a_deposit_recorded_as_the_goal_closes_does_not_get_closed_over(
    book: Book, issue_access_token
) -> None:
    """The two take the same lock on the goal: whichever is second sees
    the first. Either the deposit lands and the close is refused, or the
    close lands and the deposit moves nothing."""
    token = issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, token)
        deposit, closing = await asyncio.gather(
            _move(client, token, goal["id"], book, "deposit", "100.00"),
            client.delete(f"/api/v1/savings-goals/{goal['id']}", headers=_auth(token)),
        )

    async with db_session.async_session_factory() as session:
        stored = await session.get(SavingsGoal, uuid.UUID(goal["id"]))
    assert stored is not None
    if closing.status_code == 204:
        assert stored.closed_at is not None and stored.saved_minor == 0
        assert deposit["status_code"] == 404 or deposit["status"] == "FAILED"
        assert book.balances[book.pool] == 0
    else:
        assert closing.status_code == 409
        assert stored.closed_at is None and stored.saved_minor == 10_000
        assert book.balances[book.pool] == 10_000


async def test_what_cannot_be_done_is_refused_before_anything_moves(
    book: Book, issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    mine, theirs = issue_access_token(uuid.uuid4()), issue_access_token(uuid.uuid4())
    async with _client() as client:
        goal = await _goal(client, mine)
        url = f"/api/v1/savings-goals/{goal['id']}"

        async def refused(response_or_dict) -> tuple[int, str]:  # type: ignore[no-untyped-def]
            data = response_or_dict if isinstance(response_or_dict, dict) else {
                "status_code": response_or_dict.status_code, **response_or_dict.json()
            }
            return data["status_code"], data["title"]

        zero = await refused(await _move(client, mine, goal["id"], book, "deposit", "0"))
        words = await refused(await _move(client, mine, goal["id"], book, "deposit", "lots"))
        stranger = await refused(await _move(client, theirs, goal["id"], book, "deposit", "5"))
        stranger_sees = await client.get(f"{url}/movements", headers=_auth(theirs))
        stranger_closes = await client.delete(url, headers=_auth(theirs))
        other_wallet = await client.post(
            f"{url}/deposit",
            json={"wallet_id": str(uuid.uuid4()), "amount": "5"},
            headers={**_auth(mine), "Idempotency-Key": str(uuid.uuid4())},
        )
        no_key = await client.post(
            f"{url}/deposit", json={"wallet_id": str(book.wallet), "amount": "5"},
            headers=_auth(mine),
        )
        anonymous = await client.get("/api/v1/savings-goals")
        bad_goal = await client.post(
            "/api/v1/savings-goals",
            json={"name": "x", "currency": "EUR", "target": "10"},
            headers=_auth(mine),
        )
        no_target = await client.post(
            "/api/v1/savings-goals",
            json={"name": "x", "currency": "UZS", "target": "0"},
            headers=_auth(mine),
        )
        book.currency = "USD"
        wrong_currency = await refused(await _move(client, mine, goal["id"], book, "deposit", "5"))
        book.currency = "UZS"
        book.pool_known = False
        unavailable = await refused(await _move(client, mine, goal["id"], book, "deposit", "5"))
        monkeypatch.setattr(savings_api, "MAX_GOALS", 1)
        one_too_many = await client.post(
            "/api/v1/savings-goals",
            json={"name": "y", "currency": "UZS", "target": "10"},
            headers=_auth(mine),
        )

    assert zero == words == (422, "Invalid Amount")
    assert stranger == (404, "Savings Goal Not Found")
    assert stranger_sees.status_code == stranger_closes.status_code == 404
    assert other_wallet.status_code == 404 and other_wallet.json()["title"] == "Wallet Not Found"
    assert no_key.status_code in (400, 422)
    assert anonymous.status_code == 401
    assert bad_goal.status_code == 422 and no_target.status_code == 422
    assert wrong_currency == (422, "Currency Mismatch")
    assert unavailable == (503, "Savings Unavailable")
    assert one_too_many.status_code == 409
    assert one_too_many.json()["title"] == "Too Many Savings Goals"
    assert book.calls == 0 and book.balances == {book.wallet: 1_000_000, book.pool: 0}
