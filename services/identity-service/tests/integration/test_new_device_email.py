"""Signing in from a device the account has not used before emails the
owner."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import mailer

pytestmark = pytest.mark.usefixtures("migrated_database")

_PASSWORD = "correct-horse-battery"
_CHROME_LINUX = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/147.0.0.0 Safari/537.36"
_CHROME_LINUX_UPDATED = _CHROME_LINUX.replace("147.0.0.0", "148.0.1.2")
_SAFARI_IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 19_1 like Mac OS X) AppleWebKit/605.1.15 "
    "Version/19.1 Mobile/15E148 Safari/604.1"
)


@pytest.fixture
def notices(monkeypatch: pytest.MonkeyPatch) -> list[dict]:
    sent: list[dict] = []

    async def record(**message: object) -> None:
        sent.append(message)

    monkeypatch.setattr(settings, "smtp_host", "smtp.test")
    monkeypatch.setattr(mailer, "send_new_device", record)
    return sent


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient) -> dict:
    user = {
        "email": f"{uuid.uuid4().hex[:10]}@example.com",
        "phone": f"+99890{uuid.uuid4().int % 10**7:07d}",
        "password": _PASSWORD,
        "first_name": "Aziza",
        "last_name": "Karimova",
    }
    assert (await client.post("/api/v1/auth/register", json=user)).status_code == 201
    return user


async def _login(
    client: AsyncClient, user: dict, agent: str | None, password: str = _PASSWORD
) -> int:
    headers = {"User-Agent": agent, "X-Forwarded-For": "203.0.113.7"} if agent else {}
    response = await client.post(
        "/api/v1/auth/login", json={"email": user["email"], "password": password}, headers=headers
    )
    return response.status_code


async def test_only_a_device_the_account_has_not_used_gets_an_email(notices: list[dict]) -> None:
    async with _client() as client:
        user = await _register(client)

        # The first sign-in ever: nothing to compare with, nobody to surprise.
        assert await _login(client, user, _CHROME_LINUX) == 200
        assert notices == []

        # The same browser again, and after it updated itself.
        assert await _login(client, user, _CHROME_LINUX) == 200
        assert await _login(client, user, _CHROME_LINUX_UPDATED) == 200
        assert notices == []

        # A phone it has never been used on.
        assert await _login(client, user, _SAFARI_IPHONE) == 200
        assert len(notices) == 1
        assert notices[0]["to"] == user["email"]
        assert notices[0]["first_name"] == "Aziza"
        assert notices[0]["device"] == "Safari on iPhone"

        # Now the phone is known too.
        assert await _login(client, user, _SAFARI_IPHONE) == 200
        assert len(notices) == 1


async def test_a_failed_sign_in_sends_nothing_and_teaches_nothing(notices: list[dict]) -> None:
    async with _client() as client:
        user = await _register(client)
        await _login(client, user, _CHROME_LINUX)

        assert await _login(client, user, _SAFARI_IPHONE, password="not-the-password") == 401
        assert notices == []

        # The wrong-password attempt did not make the phone a known device.
        assert await _login(client, user, _SAFARI_IPHONE) == 200
        assert len(notices) == 1


async def test_without_a_mail_server_signing_in_just_works(
    monkeypatch: pytest.MonkeyPatch, notices: list[dict]
) -> None:
    monkeypatch.setattr(settings, "smtp_host", "")
    async with _client() as client:
        user = await _register(client)
        assert await _login(client, user, _CHROME_LINUX) == 200
        assert await _login(client, user, _SAFARI_IPHONE) == 200

    assert notices == []
