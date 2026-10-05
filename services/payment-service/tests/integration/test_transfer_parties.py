"""A transfer records who it went to, so the recipient sees it in their
history and both sides see a name."""

import uuid

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.main import app
from app.services import fraud, identity, ledger

pytestmark = pytest.mark.usefixtures("migrated_database")

_NAMES = {"sender": ("Aziza", "Karimova"), "recipient": ("Bobur", "Tursunov")}


class Parties:
    def __init__(self) -> None:
        self.sender = uuid.uuid4()
        self.recipient = uuid.uuid4()
        self.source_wallet = uuid.uuid4()
        self.destination_wallet = uuid.uuid4()


def _ledger_app(parties: Parties, *, posting_status: int = 201, owner_lookup: int = 200) -> FastAPI:
    fake = FastAPI()

    @fake.get("/api/v1/wallets/{wallet_id}")
    async def _get_wallet(wallet_id: str) -> JSONResponse:
        return JSONResponse(
            {
                "id": wallet_id,
                "card_number": "9955000000000006",
                "currency": "UZS",
                "status": "ACTIVE",
                "created_at": "2026-01-01T00:00:00Z",
                "balance_minor": 0,
                "held_minor": 0,
            }
        )

    @fake.get("/internal/v1/accounts/wallets/{wallet_id}")
    async def _owner(wallet_id: str) -> JSONResponse:
        if owner_lookup != 200 or wallet_id != str(parties.destination_wallet):
            status = 404 if owner_lookup == 200 else owner_lookup
            return JSONResponse({"title": "x", "status": status}, status_code=status)
        return JSONResponse(
            {
                "id": wallet_id,
                "owner_user_id": str(parties.recipient),
                "currency": "UZS",
                "status": "ACTIVE",
            }
        )

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
            status_code=201,
        )

    return fake


def _identity_app(parties: Parties, *, status: int = 200) -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/users/{user_id}")
    async def _user(user_id: str) -> JSONResponse:
        if status != 200:
            return JSONResponse({"title": "x", "status": status}, status_code=status)
        who = "sender" if user_id == str(parties.sender) else "recipient"
        first, last = _NAMES[who]
        return JSONResponse(
            {"id": user_id, "first_name": first, "last_name": last, "status": "ACTIVE"}
        )

    return fake


def _wire(monkeypatch: pytest.MonkeyPatch, ledger_app: FastAPI, identity_app: FastAPI) -> None:
    monkeypatch.setattr(
        ledger,
        "ledger_client",
        ledger.LedgerClient(
            base_url="http://ledger",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=ledger_app),
        ),
    )
    monkeypatch.setattr(
        identity,
        "identity_client",
        identity.IdentityClient(
            base_url="http://identity",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=identity_app),
        ),
    )
    fraud_app = FastAPI()

    @fraud_app.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": "ALLOW", "score": 10})

    monkeypatch.setattr(
        fraud,
        "fraud_client",
        fraud.FraudClient(
            base_url="http://fraud",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            fail_open_limit_minor=settings.fraud_fail_open_limit_minor,
            transport=httpx.ASGITransport(app=fraud_app),
        ),
    )


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _send(client: AsyncClient, token: str, parties: Parties) -> dict:
    response = await client.post(
        "/api/v1/transfers",
        json={
            "source_wallet_id": str(parties.source_wallet),
            "destination_wallet_id": str(parties.destination_wallet),
            "amount": "25.00",
            "currency": "UZS",
            "description": "Lunch",
        },
        headers={"Authorization": f"Bearer {token}", "Idempotency-Key": str(uuid.uuid4())},
    )
    assert response.status_code == 201
    return response.json()


async def _history(client: AsyncClient, token: str) -> list[dict]:
    response = await client.get(
        "/api/v1/transactions", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    return response.json()


async def test_both_sides_see_the_transfer_with_the_other_persons_name(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    parties = Parties()
    _wire(monkeypatch, _ledger_app(parties), _identity_app(parties))
    sender_token = issue_access_token(parties.sender)
    recipient_token = issue_access_token(parties.recipient)

    async with _client() as client:
        transfer = await _send(client, sender_token, parties)
        sent = await _history(client, sender_token)
        received = await _history(client, recipient_token)
        detail = await client.get(
            f"/api/v1/transactions/{transfer['id']}",
            headers={"Authorization": f"Bearer {recipient_token}"},
        )
        stranger = await client.get(
            f"/api/v1/transactions/{transfer['id']}",
            headers={"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"},
        )

    assert transfer["status"] == "COMPLETED"
    assert [(t["id"], t["direction"], t["counterparty_name"]) for t in sent] == [
        (transfer["id"], "OUT", "Bobur T.")
    ]
    assert [(t["id"], t["direction"], t["counterparty_name"]) for t in received] == [
        (transfer["id"], "IN", "Aziza K.")
    ]
    assert received[0]["amount_minor"] == 2500
    assert received[0]["description"] == "Lunch"
    assert detail.status_code == 200 and detail.json()["direction"] == "IN"
    assert stranger.status_code == 404


async def test_the_completed_event_names_both_sides(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    parties = Parties()
    _wire(monkeypatch, _ledger_app(parties), _identity_app(parties))

    async with _client() as client:
        transfer = await _send(client, issue_access_token(parties.sender), parties)

    async with db_session.async_session_factory() as session:
        event = (
            await session.execute(
                select(OutboxEvent).where(OutboxEvent.aggregate_id == transfer["id"])
            )
        ).scalar_one()
    assert event.event_type == "transfer.completed"
    assert event.payload["recipient_user_id"] == str(parties.recipient)
    assert event.payload["sender_name"] == "Aziza K."
    assert event.payload["recipient_name"] == "Bobur T."


async def test_a_transfer_that_failed_never_reaches_the_recipients_history(
    monkeypatch: pytest.MonkeyPatch, issue_access_token
) -> None:
    parties = Parties()
    _wire(monkeypatch, _ledger_app(parties, posting_status=409), _identity_app(parties))
    recipient_token = issue_access_token(parties.recipient)

    async with _client() as client:
        transfer = await _send(client, issue_access_token(parties.sender), parties)
        received = await _history(client, recipient_token)
        detail = await client.get(
            f"/api/v1/transactions/{transfer['id']}",
            headers={"Authorization": f"Bearer {recipient_token}"},
        )

    assert transfer["status"] == "FAILED"
    assert received == []
    assert detail.status_code == 404


@pytest.mark.parametrize(
    ("owner_lookup", "identity_status", "expected_recipient_known"),
    [(503, 200, False), (200, 503, True)],
    ids=["ledger cannot say whose wallet", "identity cannot give names"],
)
async def test_money_still_moves_when_the_parties_cannot_be_looked_up(
    monkeypatch: pytest.MonkeyPatch,
    issue_access_token,
    owner_lookup: int,
    identity_status: int,
    expected_recipient_known: bool,
) -> None:
    parties = Parties()
    _wire(
        monkeypatch,
        _ledger_app(parties, owner_lookup=owner_lookup),
        _identity_app(parties, status=identity_status),
    )
    sender_token = issue_access_token(parties.sender)

    async with _client() as client:
        transfer = await _send(client, sender_token, parties)
        sent = await _history(client, sender_token)
        received = await _history(client, issue_access_token(parties.recipient))

    assert transfer["status"] == "COMPLETED"
    assert sent[0]["direction"] == "OUT" and sent[0]["counterparty_name"] is None
    # With the owner known the recipient still sees it, just without a name.
    assert [t["counterparty_name"] for t in received] == (
        [None] if expected_recipient_known else []
    )
