import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_USER = {
    "email": "knuth@example.com",
    "phone": "+998905556677",
    "password": "art-of-programming-1968",
    "first_name": "Donald",
    "last_name": "Knuth",
}
_NEW = "literate-programming-1984"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, password: str, agent: str = "Laptop") -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": _USER["email"], "password": password},
        headers={"User-Agent": agent},
    )
    return {"status": response.status_code, **(response.json() if response.is_success else {})}


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _change(client: AsyncClient, tokens: dict, current: str, new: str):
    return await client.post(
        "/api/v1/users/me/password",
        json={"current_password": current, "new_password": new},
        headers=_auth(tokens),
    )


async def test_changing_the_password_signs_out_every_other_device() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        laptop = await _login(client, _USER["password"], "Laptop")
        phone = await _login(client, _USER["password"], "Phone")

        changed = await _change(client, laptop, _USER["password"], _NEW)
        phone_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": phone["refresh_token"]}
        )
        laptop_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": laptop["refresh_token"]}
        )
        old_login = await _login(client, _USER["password"])
        new_login = await _login(client, _NEW)

    assert changed.status_code == 204
    assert phone_refresh.status_code == 401
    assert laptop_refresh.status_code == 200  # the device that made the change stays in
    assert old_login["status"] == 401
    assert new_login["status"] == 200

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent).where(OutboxEvent.event_type == "user.password_changed")
        )
        [event] = result.scalars().all()
    assert event.payload["sessions_revoked"] == 1


async def test_a_wrong_current_password_changes_nothing() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        tokens = await _login(client, _USER["password"])

        wrong = await _change(client, tokens, "not-my-password", _NEW)
        same = await _change(client, tokens, _USER["password"], _USER["password"])
        short = await _change(client, tokens, _USER["password"], "short")
        still_old = await _login(client, _USER["password"])

    # 422, never 401: the caller's session is fine, only the input is wrong.
    assert wrong.status_code == 422
    assert wrong.json()["title"] == "Incorrect Password"
    assert same.status_code == 422
    assert same.json()["title"] == "Password Unchanged"
    assert short.status_code == 422
    assert still_old["status"] == 200


async def test_changing_the_password_needs_a_token() -> None:
    async with _client() as client:
        response = await client.post(
            "/api/v1/users/me/password",
            json={"current_password": "x", "new_password": "long-enough-1"},
        )

    assert response.status_code == 401
