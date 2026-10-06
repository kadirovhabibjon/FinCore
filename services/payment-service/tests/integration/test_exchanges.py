"""Currency exchange between a customer's own wallets: two ledger
postings that must both happen or neither."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, update

from app.core.config import settings
from app.db import session as db_session
from app.domain.exchange import Exchange, ExchangeStatus
from app.domain.outbox import OutboxEvent
from app.main import app
from app.services import ledger, rates
from app.services.rates import Rates
from app.services.recovery import resolve_stuck_exchanges

pytestmark = pytest.mark.usefixtures("migrated_database")

UZS_PER_USD = "12000"


class Ledger:
    """A ledger-service that records postings and can be told how to
    answer each step of an exchange ("sell", "buy", "reverse")."""

    def __init__(self) -> None:
        self.owner = uuid.uuid4()
        self.uzs_wallet = uuid.uuid4()
        self.usd_wallet = uuid.uuid4()
        self.positions = {"UZS": uuid.uuid4(), "USD": uuid.uuid4()}
        self.postings: list[dict] = []
        # step -> HTTP status to answer with ("down" = no answer at all).
        self.answers: dict[str, int | str] = {}
        self.system_accounts_available = True

    def currency_of(self, wallet_id: str) -> str | None:
        return {str(self.uzs_wallet): "UZS", str(self.usd_wallet): "USD"}.get(wallet_id)

    def app(self) -> FastAPI:
        fake = FastAPI()

        @fake.get("/api/v1/wallets/{wallet_id}")
        async def _wallet(wallet_id: str) -> JSONResponse:
            currency = self.currency_of(wallet_id)
            if currency is None:
                return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
            return JSONResponse(
                {
                    "id": wallet_id,
                    "card_number": "9955000000000006",
                    "currency": currency,
                    "status": "ACTIVE",
                    "created_at": "2026-01-01T00:00:00Z",
                    "balance_minor": 0,
                    "held_minor": 0,
                }
            )

        @fake.get("/internal/v1/accounts/system")
        async def _system(kind: str, currency: str) -> JSONResponse:
            if not self.system_accounts_available or kind != "EXCHANGE":
                return JSONResponse({"title": "x", "status": 404}, status_code=404)
            return JSONResponse(
                {
                    "id": str(self.positions[currency]),
                    "kind": kind,
                    "currency": currency,
                    "status": "ACTIVE",
                    "created_at": "2026-01-01T00:00:00Z",
                }
            )

        @fake.post("/internal/v1/postings")
        async def _posting(request: Request) -> JSONResponse:
            payload = await request.json()
            step = payload["source_id"].rsplit(":", 1)[-1]
            answer = self.answers.get(step, 201)
            if answer == "down":
                return JSONResponse({"title": "x", "status": 503}, status_code=503)
            if isinstance(answer, int) and answer >= 400:
                return JSONResponse(
                    {
                        "title": "Insufficient Funds" if step == "sell" else "Account Not Active",
                        "status": answer,
                    },
                    status_code=answer,
                )
            if payload["source_id"] not in {p["source_id"] for p in self.postings}:
                self.postings.append(payload)  # idempotent on source_id, like the real one
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

    def steps(self) -> list[str]:
        return [p["source_id"].rsplit(":", 1)[-1] for p in self.postings]


@pytest.fixture
def book(monkeypatch: pytest.MonkeyPatch) -> Ledger:
    book = Ledger()
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=book.app()),
        ),
    )

    async def fixed_rates() -> Rates:
        return Rates(
            per_usd={"USD": Decimal("1"), "UZS": Decimal(UZS_PER_USD)},
            updated_at=datetime(2026, 10, 6, tzinfo=UTC),
            fetched=0.0,
        )

    monkeypatch.setattr(rates, "current_rates", fixed_rates)
    return book


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _exchange(
    client: AsyncClient,
    token: str,
    book: Ledger,
    *,
    amount: str = "1200000.00",
    expected: int = 100_00,
    key: str | None = None,
    source: uuid.UUID | None = None,
    destination: uuid.UUID | None = None,
) -> httpx.Response:
    return await client.post(
        "/api/v1/exchanges",
        json={
            "source_wallet_id": str(source or book.uzs_wallet),
            "destination_wallet_id": str(destination or book.usd_wallet),
            "amount": amount,
            "expected_destination_amount_minor": expected,
        },
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )


async def _stored(exchange_id: str) -> Exchange:
    async with db_session.async_session_factory() as session:
        exchange = await session.get(Exchange, uuid.UUID(exchange_id))
        assert exchange is not None
        return exchange


async def _events(exchange_id: str) -> list[str]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent.event_type).where(OutboxEvent.aggregate_id == exchange_id)
        )
        return list(result.scalars().all())


async def _make_stuck(exchange_id: str) -> None:
    async with db_session.async_session_factory() as session:
        await session.execute(
            update(Exchange)
            .where(Exchange.id == uuid.UUID(exchange_id))
            .values(updated_at=datetime.now(UTC) - timedelta(minutes=10))
        )
        await session.commit()


async def _recover() -> list[Exchange]:
    async with db_session.async_session_factory() as session:
        return await resolve_stuck_exchanges(session, stuck_after_seconds=60)


async def test_a_quote_says_what_the_amount_buys_and_moves_nothing(
    book: Ledger, issue_access_token
) -> None:
    token = issue_access_token(book.owner)
    async with _client() as client:
        response = await client.get(
            "/api/v1/exchanges/quote",
            params={
                "source_wallet_id": str(book.uzs_wallet),
                "destination_wallet_id": str(book.usd_wallet),
                "amount": "1200000.00",
            },
            headers=_auth(token),
        )
        back = await client.get(
            "/api/v1/exchanges/quote",
            params={
                "source_wallet_id": str(book.usd_wallet),
                "destination_wallet_id": str(book.uzs_wallet),
                "amount": "100",
            },
            headers=_auth(token),
        )

    assert response.status_code == 200
    assert response.json() == {
        "source_amount_minor": 1_200_000_00,
        "source_currency": "UZS",
        "destination_amount_minor": 100_00,
        "destination_currency": "USD",
        "rate": "0.000083333333333",
        "rate_updated_at": "2026-10-06T00:00:00Z",
    }
    assert (back.json()["destination_amount_minor"], back.json()["rate"]) == (1_200_000_00, "12000")
    assert book.postings == []


async def test_an_exchange_is_a_sale_then_a_purchase_each_balanced_in_its_currency(
    book: Ledger, issue_access_token
) -> None:
    token = issue_access_token(book.owner)
    async with _client() as client:
        key = str(uuid.uuid4())
        response = await _exchange(client, token, book, key=key)
        replay = await _exchange(client, token, book, key=key)
        fetched = await client.get(
            f"/api/v1/exchanges/{response.json()['id']}", headers=_auth(token)
        )
        history = (await client.get("/api/v1/transactions", headers=_auth(token))).json()
        hidden = await client.get(
            f"/api/v1/exchanges/{response.json()['id']}",
            headers=_auth(issue_access_token(uuid.uuid4())),
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "COMPLETED" and body["reference"].startswith("EXC-")
    assert (body["source_amount_minor"], body["destination_amount_minor"]) == (1_200_000_00, 100_00)
    assert replay.json() == body and fetched.json() == body and hidden.status_code == 404

    sell, buy = book.postings  # exactly two, even after the replay
    exchange_id = body["id"]
    assert sell == {
        "source_service": "payment-service",
        "source_id": f"{exchange_id}:sell",
        "type": "EXCHANGE",
        "currency": "UZS",
        "entries": [
            {
                "account_id": str(book.uzs_wallet),
                "direction": "DEBIT",
                "amount_minor": 1_200_000_00,
            },
            {
                "account_id": str(book.positions["UZS"]),
                "direction": "CREDIT",
                "amount_minor": 1_200_000_00,
            },
        ],
    }
    assert buy == {
        "source_service": "payment-service",
        "source_id": f"{exchange_id}:buy",
        "type": "EXCHANGE",
        "currency": "USD",
        "entries": [
            {
                "account_id": str(book.positions["USD"]),
                "direction": "DEBIT",
                "amount_minor": 100_00,
            },
            {"account_id": str(book.usd_wallet), "direction": "CREDIT", "amount_minor": 100_00},
        ],
    }
    assert await _events(exchange_id) == ["exchange.completed"]
    assert [
        (
            t["type"],
            t["direction"],
            t["amount_minor"],
            t["currency"],
            t["received_amount_minor"],
            t["received_currency"],
        )
        for t in history
    ] == [("EXCHANGE", "SELF", 1_200_000_00, "UZS", 100_00, "USD")]


async def test_a_different_amount_than_the_one_agreed_to_exchanges_nothing(
    book: Ledger, issue_access_token
) -> None:
    token = issue_access_token(book.owner)
    async with _client() as client:
        key = str(uuid.uuid4())
        stale = await _exchange(client, token, book, expected=101_00, key=key)
        # The key was not consumed: confirming the new amount with it works.
        confirmed = await _exchange(client, token, book, expected=100_00, key=key)

    assert stale.status_code == 409 and stale.json()["title"] == "Rate Changed"
    assert confirmed.status_code == 201
    assert book.steps() == ["sell", "buy"]


async def test_when_the_sale_is_refused_nothing_moves(book: Ledger, issue_access_token) -> None:
    book.answers["sell"] = 409
    async with _client() as client:
        response = await _exchange(client, issue_access_token(book.owner), book)

    assert response.status_code == 201
    assert response.json()["status"] == "FAILED"
    assert response.json()["failure_reason"] == "Insufficient Funds"
    assert book.postings == []
    assert await _events(response.json()["id"]) == ["exchange.failed"]


async def test_when_the_purchase_is_refused_the_sale_is_undone(
    book: Ledger, issue_access_token
) -> None:
    book.answers["buy"] = 409
    async with _client() as client:
        response = await _exchange(client, issue_access_token(book.owner), book)

    assert response.json()["status"] == "FAILED"
    assert response.json()["failure_reason"] == "Account Not Active"
    assert book.steps() == ["sell", "reverse"]
    reverse = book.postings[1]
    # Exactly the sale, the other way round.
    assert reverse["currency"] == "UZS"
    assert reverse["entries"] == [
        {
            "account_id": str(book.positions["UZS"]),
            "direction": "DEBIT",
            "amount_minor": 1_200_000_00,
        },
        {"account_id": str(book.uzs_wallet), "direction": "CREDIT", "amount_minor": 1_200_000_00},
    ]
    assert await _events(response.json()["id"]) == ["exchange.failed"]


@pytest.mark.parametrize(
    ("lost_step", "left_as", "already_posted"),
    [("sell", "PENDING", []), ("buy", "DEBITED", ["sell"])],
    ids=["no answer to the sale", "no answer to the purchase"],
)
async def test_an_exchange_interrupted_mid_way_is_finished_by_recovery(
    book: Ledger, issue_access_token, lost_step: str, left_as: str, already_posted: list[str]
) -> None:
    """The dangerous case is the second: the customer's UZS is gone and
    their USD has not arrived. It must not stay that way."""
    book.answers[lost_step] = "down"
    async with _client() as client:
        response = await _exchange(client, issue_access_token(book.owner), book)
    exchange_id = response.json()["id"]

    assert response.status_code == 201 and response.json()["status"] == left_as
    # In history the customer sees one thing: it is being carried out.
    async with _client() as client:
        token = issue_access_token(book.owner)
        [shown] = (await client.get("/api/v1/transactions", headers=_auth(token))).json()
    assert shown["status"] == "PROCESSING"
    assert book.steps() == already_posted
    assert await _events(exchange_id) == []

    assert await _recover() == []  # too recent: the request may still be running
    await _make_stuck(exchange_id)
    assert await _recover() != []  # ledger still down: tried, nothing changed
    assert (await _stored(exchange_id)).status == ExchangeStatus(left_as)

    book.answers.clear()
    await _make_stuck(exchange_id)
    [finished] = await _recover()

    assert finished.status == ExchangeStatus.COMPLETED
    assert book.steps() == ["sell", "buy"]  # each exactly once
    assert await _events(exchange_id) == ["exchange.completed"]
    assert await _recover() == []


async def test_a_refund_that_cannot_be_posted_yet_is_retried_until_it_is(
    book: Ledger, issue_access_token
) -> None:
    book.answers.update({"buy": 409, "reverse": "down"})
    async with _client() as client:
        response = await _exchange(client, issue_access_token(book.owner), book)
    exchange_id = response.json()["id"]

    assert response.json()["status"] == "REVERSING"
    assert book.steps() == ["sell"]

    book.answers["reverse"] = 201
    await _make_stuck(exchange_id)
    [finished] = await _recover()

    assert finished.status == ExchangeStatus.FAILED
    assert book.steps() == ["sell", "reverse"]
    assert await _events(exchange_id) == ["exchange.failed"]


async def test_what_cannot_be_exchanged_is_refused_before_anything_moves(
    book: Ledger, issue_access_token
) -> None:
    token = issue_access_token(book.owner)
    async with _client() as client:
        same = await _exchange(client, token, book, destination=book.uzs_wallet)
        not_mine = await _exchange(client, token, book, source=uuid.uuid4())
        too_small = await _exchange(client, token, book, amount="100.00", expected=1)
        zero = await _exchange(client, token, book, amount="0")
        fraction = await _exchange(client, token, book, amount="1.005")
        anonymous = await client.post("/api/v1/exchanges", json={})
        no_key = await client.post(
            "/api/v1/exchanges",
            json={
                "source_wallet_id": str(book.uzs_wallet),
                "destination_wallet_id": str(book.usd_wallet),
                "amount": "1200000.00",
                "expected_destination_amount_minor": 100_00,
            },
            headers=_auth(token),
        )

    assert same.status_code == 422 and same.json()["title"] == "Same Currency"
    assert not_mine.status_code == 404
    assert too_small.status_code == 422 and too_small.json()["title"] == "Amount Too Small"
    assert zero.status_code == fraction.status_code == 422
    assert anonymous.status_code == 401
    assert no_key.status_code == 422
    assert book.postings == []


async def test_without_rates_or_accounts_exchange_is_unavailable_not_broken(
    book: Ledger, issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = issue_access_token(book.owner)
    async with _client() as client:
        book.system_accounts_available = False
        no_accounts = await _exchange(client, token, book)
        book.system_accounts_available = True

        async def no_rates() -> Rates:
            raise rates.RatesUnavailableError("down")

        monkeypatch.setattr(rates, "current_rates", no_rates)
        no_rate = await _exchange(client, token, book)

    assert no_accounts.status_code == no_rate.status_code == 503
    assert no_rate.json()["title"] == "Exchange Unavailable"
    assert book.postings == []
