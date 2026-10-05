"""The bell in the web app: a customer's own notifications, how many are
unread, and marking them read."""

import base64
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fincore_common import EventEnvelope, EventType, JWTVerifier
from httpx import ASGITransport, AsyncClient

from app.core import auth as auth_module
from app.core.config import settings
from app.main import app
from app.services.consumer import handle_transfer_event

pytestmark = pytest.mark.usefixtures("migrated_database")


@pytest.fixture
def issue(monkeypatch: pytest.MonkeyPatch) -> Callable[[uuid.UUID], str]:
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    jwks_app = FastAPI()

    @jwks_app.get("/.well-known/jwks.json")
    async def _jwks() -> dict:
        return {"keys": [{"kty": "OKP", "crv": "Ed25519", "x": x, "kid": "k", "alg": "EdDSA"}]}

    monkeypatch.setattr(
        auth_module,
        "jwt_verifier",
        JWTVerifier(
            jwks_url="http://identity/.well-known/jwks.json",
            issuer=settings.jwt_issuer,
            transport=httpx.ASGITransport(app=jwks_app),
        ),
    )

    def _issue(user_id: uuid.UUID) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(user_id),
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        }
        return jwt.encode(claims, pem, algorithm="EdDSA", headers={"kid": "k"})

    return _issue


async def _transfer(sender: uuid.UUID, recipient: uuid.UUID, amount_minor: int) -> None:
    envelope = EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED,
        producer="payment-service",
        data={
            "transfer_id": str(uuid.uuid4()),
            "reference": "TRF-BELL",
            "initiator_user_id": str(sender),
            "recipient_user_id": str(recipient),
            "sender_name": "Aziza K.",
            "recipient_name": "Bobur T.",
            "amount_minor": amount_minor,
            "currency": "UZS",
            "status": "COMPLETED",
            "failure_reason": None,
            "completed_at": "2026-01-01T00:00:00Z",
        },
    )
    await handle_transfer_event(envelope, providers=[])


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_each_side_of_a_transfer_finds_their_own_notification(
    issue: Callable[[uuid.UUID], str],
) -> None:
    sender, recipient = uuid.uuid4(), uuid.uuid4()
    await _transfer(sender, recipient, 1_250_000)

    async with _client() as client:
        sent = await client.get(
            "/api/v1/notifications", headers={"Authorization": f"Bearer {issue(sender)}"}
        )
        received = await client.get(
            "/api/v1/notifications", headers={"Authorization": f"Bearer {issue(recipient)}"}
        )
        stranger = await client.get(
            "/api/v1/notifications", headers={"Authorization": f"Bearer {issue(uuid.uuid4())}"}
        )

    assert sent.status_code == 200
    assert sent.json()["unread_count"] == 1
    [mine] = sent.json()["items"]
    assert mine["type"] == "transfer.completed"
    assert mine["title"] == "Transfer completed"
    assert mine["body"] == "You sent 12,500.00 UZS to Bobur T. — reference TRF-BELL"
    assert mine["read"] is False

    [theirs] = received.json()["items"]
    assert theirs["type"] == "transfer.received"
    assert theirs["title"] == "Money received"
    assert theirs["body"] == "Aziza K. sent you 12,500.00 UZS."

    assert stranger.json() == {"unread_count": 0, "items": []}


async def test_opening_the_bell_marks_only_the_callers_notifications_read(
    issue: Callable[[uuid.UUID], str],
) -> None:
    sender, recipient = uuid.uuid4(), uuid.uuid4()
    await _transfer(sender, recipient, 100)
    await _transfer(sender, recipient, 200)
    mine = {"Authorization": f"Bearer {issue(recipient)}"}
    theirs = {"Authorization": f"Bearer {issue(sender)}"}

    async with _client() as client:
        before = (await client.get("/api/v1/notifications", headers=mine)).json()
        first = await client.post("/api/v1/notifications/read", headers=mine)
        again = await client.post("/api/v1/notifications/read", headers=mine)
        after = (await client.get("/api/v1/notifications", headers=mine)).json()
        other = (await client.get("/api/v1/notifications", headers=theirs)).json()

    assert before["unread_count"] == 2
    assert first.status_code == again.status_code == 204
    assert after["unread_count"] == 0
    assert [item["read"] for item in after["items"]] == [True, True]
    assert other["unread_count"] == 2


async def test_the_count_covers_everything_unread_not_just_the_page(
    issue: Callable[[uuid.UUID], str],
) -> None:
    sender, recipient = uuid.uuid4(), uuid.uuid4()
    for amount in (100, 200, 300):
        await _transfer(sender, recipient, amount)

    async with _client() as client:
        page = (
            await client.get(
                "/api/v1/notifications",
                params={"limit": 2},
                headers={"Authorization": f"Bearer {issue(recipient)}"},
            )
        ).json()

    assert page["unread_count"] == 3
    assert len(page["items"]) == 2


async def test_needs_a_valid_token(issue: Callable[[uuid.UUID], str]) -> None:
    async with _client() as client:
        assert (await client.get("/api/v1/notifications")).status_code == 401
        assert (await client.post("/api/v1/notifications/read")).status_code == 401
        forged = await client.get(
            "/api/v1/notifications", headers={"Authorization": "Bearer forged"}
        )
    assert forged.status_code == 401
