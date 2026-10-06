"""Asking another customer for money: nothing moves until they pay, and
a request can be paid exactly once."""

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

from app.core.config import settings
from app.db import session as db_session
from app.domain.money_request import MoneyRequest, MoneyRequestStatus
from app.domain.outbox import OutboxEvent
from app.domain.transfer import Transfer, TransferStatus
from app.main import app
from app.services import fraud, identity, ledger

pytestmark = pytest.mark.usefixtures("migrated_database")


class World:
    """Two customers with a UZS wallet each (and the payer a USD one)."""

    def __init__(self) -> None:
        self.requester = uuid.uuid4()
        self.payer = uuid.uuid4()
        self.requester_wallet = uuid.uuid4()
        self.payer_wallet = uuid.uuid4()
        self.payer_usd_wallet = uuid.uuid4()
        self.payer_card = generate_card_number()
        self.payer_usd_card = generate_card_number()
        self.requester_card = generate_card_number()
        self.postings: list[dict] = []
        self.posting_status = 201
        self.fraud_decision = "ALLOW"

    def wallet(self, wallet_id: str) -> dict | None:
        table = {
            str(self.requester_wallet): (self.requester, "UZS", self.requester_card),
            str(self.payer_wallet): (self.payer, "UZS", self.payer_card),
            str(self.payer_usd_wallet): (self.payer, "USD", self.payer_usd_card),
        }
        if wallet_id not in table:
            return None
        owner, currency, card = table[wallet_id]
        return {
            "id": wallet_id,
            "owner_user_id": str(owner),
            "card_number": card,
            "currency": currency,
            "status": "ACTIVE",
        }


def _ledger_app(world: World) -> FastAPI:
    fake = FastAPI()

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _get_wallet(wallet_id: str) -> JSONResponse:
        wallet = world.wallet(wallet_id)
        if wallet is None:
            return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)
        return JSONResponse(
            {**wallet, "created_at": "2026-01-01T00:00:00Z", "balance_minor": 0, "held_minor": 0}
        )

    @fake.get("/internal/v1/accounts/wallet-by-card")
    async def _by_card(card_number: str) -> JSONResponse:
        for wallet_id in (world.requester_wallet, world.payer_wallet, world.payer_usd_wallet):
            wallet = world.wallet(str(wallet_id))
            if wallet and wallet["card_number"] == card_number:
                return JSONResponse(wallet)
        return JSONResponse({"title": "Wallet Not Found", "status": 404}, status_code=404)

    @fake.get("/internal/v1/accounts/wallets/{wallet_id}")
    async def _owner(wallet_id: str) -> JSONResponse:
        wallet = world.wallet(wallet_id)
        if wallet is None:
            return JSONResponse({"title": "x", "status": 404}, status_code=404)
        return JSONResponse(wallet)

    @fake.post("/internal/v1/postings")
    async def _post_posting(request: Request) -> JSONResponse:
        payload = await request.json()
        if world.posting_status >= 400:
            return JSONResponse(
                {"title": "Insufficient Funds", "status": world.posting_status},
                status_code=world.posting_status,
            )
        world.postings.append(payload)
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


@pytest.fixture
def world(monkeypatch: pytest.MonkeyPatch) -> World:
    world = World()
    identity_app = FastAPI()

    @identity_app.get("/internal/v1/users/{user_id}")
    async def _user(user_id: str) -> JSONResponse:
        first, last = ("Aziza", "Karimova") if user_id == str(world.requester) else ("Bobur", "Ts")
        return JSONResponse(
            {"id": user_id, "first_name": first, "last_name": last, "status": "ACTIVE"}
        )

    fraud_app = FastAPI()

    @fraud_app.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": world.fraud_decision, "score": 10})

    token = settings.internal_service_token
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_ledger_app(world)),
        ),
    )
    monkeypatch.setattr(
        identity,
        "identity_client",
        identity.IdentityClient(
            base_url="http://identity",
            internal_token=token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=identity_app),
        ),
    )
    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud",
            internal_token=token,
            timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=httpx.ASGITransport(app=fraud_app),
        ),
    )
    return world


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _ask(
    client: AsyncClient, token: str, world: World, *, amount: str = "500.00", **overrides: str
) -> httpx.Response:
    body = {
        "wallet_id": str(world.requester_wallet),
        "from_card_number": world.payer_card,
        "amount": amount,
        "note": "Dinner",
        **overrides,
    }
    return await client.post("/api/v1/money-requests", json=body, headers=_auth(token))


async def _pay(
    client: AsyncClient, token: str, world: World, request_id: str, key: str | None = None
) -> httpx.Response:
    return await client.post(
        f"/api/v1/money-requests/{request_id}/pay",
        json={"source_wallet_id": str(world.payer_wallet)},
        headers={**_auth(token), "Idempotency-Key": key or str(uuid.uuid4())},
    )


async def _listed(client: AsyncClient, token: str) -> list[dict]:
    response = await client.get("/api/v1/money-requests", headers=_auth(token))
    assert response.status_code == 200
    return response.json()


async def test_a_request_reaches_the_person_asked_and_moves_nothing(
    world: World, issue_access_token
) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    async with _client() as client:
        created = await _ask(client, asker, world)
        mine = await _listed(client, asker)
        theirs = await _listed(client, asked)
        strangers = await _listed(client, issue_access_token(uuid.uuid4()))

    assert created.status_code == 201
    request = created.json()
    assert request["reference"].startswith("REQ-")
    assert (request["direction"], request["status"]) == ("OUTGOING", "PENDING")
    assert (request["amount_minor"], request["currency"], request["note"]) == (
        50_000,
        "UZS",
        "Dinner",
    )
    assert request["counterparty_name"] == "Bobur T."
    assert [r["id"] for r in mine] == [request["id"]]
    [incoming] = theirs
    assert (incoming["direction"], incoming["counterparty_name"]) == ("INCOMING", "Aziza K.")
    assert strangers == []
    assert world.postings == []

    async with db_session.async_session_factory() as session:
        event = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == request["id"])
            )
        ).scalar_one()
    assert event.event_type == "money_request.created"
    assert event.payload["payer_user_id"] == str(world.payer)
    assert event.payload["actor_user_id"] == str(world.requester)
    assert event.payload["requester_name"] == "Aziza K."


async def test_paying_a_request_is_a_transfer_to_the_requesters_wallet(
    world: World, issue_access_token
) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    async with _client() as client:
        request = (await _ask(client, asker, world)).json()
        key = str(uuid.uuid4())
        paid = await _pay(client, asked, world, request["id"], key)
        replayed = await _pay(client, asked, world, request["id"], key)
        again = await _pay(client, asked, world, request["id"])
        history = (await client.get("/api/v1/transactions", headers=_auth(asker))).json()
        [seen_by_asker] = await _listed(client, asker)

    assert paid.status_code == 200
    assert paid.json()["status"] == "PAID"
    # A retry of the same request is answered from the record, not paid again...
    assert replayed.status_code == 200 and replayed.json() == paid.json()
    # ...and a new attempt is refused.
    assert again.status_code == 409 and again.json()["title"] == "Money Request Not Open"
    assert len(world.postings) == 1

    async with db_session.async_session_factory() as session:
        transfer = await session.get(Transfer, uuid.UUID(paid.json()["transfer_id"]))
    assert transfer is not None
    assert transfer.initiator_user_id == world.payer
    assert transfer.source_wallet_id == world.payer_wallet
    assert transfer.destination_wallet_id == world.requester_wallet
    assert (transfer.amount_minor, transfer.currency) == (50_000, "UZS")
    assert transfer.description == "Dinner"
    # The requester sees the money arrive like any other transfer.
    assert [(t["direction"], t["counterparty_name"]) for t in history] == [("IN", "Bobur T.")]
    assert seen_by_asker["status"] == "PAID"


async def test_two_payments_at_once_pay_it_once(world: World, issue_access_token) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    async with _client() as client:
        request = (await _ask(client, asker, world)).json()
        first, second = await asyncio.gather(
            _pay(client, asked, world, request["id"]), _pay(client, asked, world, request["id"])
        )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
    assert len(world.postings) == 1


async def test_a_payment_that_fails_leaves_the_request_open_to_pay_again(
    world: World, issue_access_token
) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    async with _client() as client:
        request = (await _ask(client, asker, world)).json()
        world.posting_status = 409
        failed = await _pay(client, asked, world, request["id"])
        world.posting_status = 201
        paid = await _pay(client, asked, world, request["id"])

    assert failed.status_code == 200
    assert failed.json()["status"] == "PENDING"
    assert failed.json()["last_failure"] == "Insufficient Funds"
    assert paid.json()["status"] == "PAID"
    assert len(world.postings) == 1


async def test_a_payment_held_for_review_shows_as_processing_until_it_ends(
    world: World, issue_access_token
) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    world.fraud_decision = "REVIEW"
    async with _client() as client:
        request = (await _ask(client, asker, world)).json()
        held = await _pay(client, asked, world, request["id"])
        while_held = await _pay(client, asked, world, request["id"])
        decline_while_held = await client.post(
            f"/api/v1/money-requests/{request['id']}/decline", headers=_auth(asked)
        )

        # An admin approves the review: the transfer completes later.
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Transfer)
                .where(Transfer.id == uuid.UUID(held.json()["transfer_id"]))
                .values(status=TransferStatus.COMPLETED)
            )
            await session.commit()
        [after] = await _listed(client, asker)

    assert held.json()["status"] == "PROCESSING"
    assert while_held.status_code == 409 and decline_while_held.status_code == 409
    assert after["status"] == "PAID"
    assert world.postings == []  # held before any money moved


async def test_declining_and_cancelling_are_for_the_right_person_and_only_once(
    world: World, issue_access_token
) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    stranger = issue_access_token(uuid.uuid4())
    async with _client() as client:
        first = (await _ask(client, asker, world)).json()
        second = (await _ask(client, asker, world, amount="10.00")).json()

        def act(request_id: str, action: str, token: str):
            return client.post(
                f"/api/v1/money-requests/{request_id}/{action}", headers=_auth(token)
            )

        wrong_decline = await act(first["id"], "decline", asker)
        wrong_cancel = await act(first["id"], "cancel", asked)
        hidden = await act(first["id"], "decline", stranger)
        declined = await act(first["id"], "decline", asked)
        declined_twice = await act(first["id"], "decline", asked)
        pay_declined = await _pay(client, asked, world, first["id"])
        cancelled = await act(second["id"], "cancel", asker)
        pay_cancelled = await _pay(client, asked, world, second["id"])
        stranger_pays = await _pay(client, stranger, world, second["id"])

    assert wrong_decline.status_code == wrong_cancel.status_code == hidden.status_code == 404
    assert declined.status_code == 200 and declined.json()["status"] == "DECLINED"
    assert declined_twice.status_code == pay_declined.status_code == 409
    assert cancelled.json()["status"] == "CANCELLED"
    assert pay_cancelled.status_code == 409
    assert stranger_pays.status_code == 404
    assert world.postings == []

    async with db_session.async_session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OutboxEvent.event_type).where(OutboxEvent.aggregate_id == first["id"])
                )
            )
            .scalars()
            .all()
        )
    assert sorted(events) == ["money_request.created", "money_request.declined"]


async def test_what_can_be_asked_for_is_validated(world: World, issue_access_token) -> None:
    asker = issue_access_token(world.requester)
    async with _client() as client:
        own_card = await _ask(client, asker, world, from_card_number=world.requester_card)
        other_currency = await _ask(client, asker, world, from_card_number=world.payer_usd_card)
        nobody = await _ask(client, asker, world, from_card_number=generate_card_number())
        typo = await _ask(client, asker, world, from_card_number="9955123456789012")
        zero = await _ask(client, asker, world, amount="0")
        fraction = await _ask(client, asker, world, amount="1.005")
        not_my_wallet = await _ask(client, asker, world, wallet_id=str(uuid.uuid4()))
        anonymous = await client.post("/api/v1/money-requests", json={})

    assert own_card.status_code == 422
    assert own_card.json()["title"] == "Cannot Request From Yourself"
    assert other_currency.status_code == 422
    assert other_currency.json()["title"] == "Currency Mismatch"
    assert nobody.status_code == 404
    assert typo.status_code == zero.status_code == fraction.status_code == 422
    assert not_my_wallet.status_code == 404
    assert anonymous.status_code == 401


async def test_one_person_cannot_be_pestered_with_requests(
    world: World, issue_access_token
) -> None:
    asker = issue_access_token(world.requester)
    async with _client() as client:
        statuses = [(await _ask(client, asker, world)).status_code for _ in range(4)]
        [newest, *_] = await _listed(client, asker)
        await client.post(f"/api/v1/money-requests/{newest['id']}/cancel", headers=_auth(asker))
        after_cancelling_one = await _ask(client, asker, world)

    assert statuses == [201, 201, 201, 429]
    assert after_cancelling_one.status_code == 201


async def test_a_claim_abandoned_by_a_crash_does_not_lock_the_request_forever(
    world: World, issue_access_token
) -> None:
    asker, asked = issue_access_token(world.requester), issue_access_token(world.payer)
    async with _client() as client:
        request = (await _ask(client, asker, world)).json()
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(MoneyRequest)
                .where(MoneyRequest.id == uuid.UUID(request["id"]))
                .values(status=MoneyRequestStatus.PAYING, updated_at=datetime.now(UTC))
            )
            await session.commit()
        [just_claimed] = await _listed(client, asked)
        refused = await _pay(client, asked, world, request["id"])

        async with db_session.async_session_factory() as session:
            await session.execute(
                update(MoneyRequest)
                .where(MoneyRequest.id == uuid.UUID(request["id"]))
                .values(updated_at=datetime.now(UTC) - timedelta(minutes=5))
            )
            await session.commit()
        paid = await _pay(client, asked, world, request["id"])

    assert just_claimed["status"] == "PROCESSING"
    assert refused.status_code == 409
    assert paid.json()["status"] == "PAID"
