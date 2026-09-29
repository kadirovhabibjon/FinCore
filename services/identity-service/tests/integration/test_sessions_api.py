import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_USER = {
    "email": "hopper@example.com",
    "phone": "+998901112233",
    "password": "cobol-and-bugs-1947",
    "first_name": "Grace",
    "last_name": "Hopper",
}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient, user_agent: str) -> dict:
    response = await client.post(
        "/api/v1/auth/login",
        json={"email": _USER["email"], "password": _USER["password"]},
        headers={"User-Agent": user_agent, "X-Real-IP": "203.0.113.7"},
    )
    assert response.status_code == 200
    return response.json()


def _auth(tokens: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def test_sessions_are_listed_with_the_current_one_marked() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        laptop = await _login(client, "Laptop/1.0")
        await _login(client, "Phone/2.0")

        response = await client.get("/api/v1/users/me/sessions", headers=_auth(laptop))

    assert response.status_code == 200
    sessions = response.json()
    assert len(sessions) == 2
    current = [s for s in sessions if s["current"]]
    assert len(current) == 1
    assert current[0]["user_agent"] == "Laptop/1.0"
    assert current[0]["ip_address"] == "203.0.113.7"
    assert {s["user_agent"] for s in sessions} == {"Laptop/1.0", "Phone/2.0"}


async def test_revoking_another_session_kills_its_refresh_token() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        laptop = await _login(client, "Laptop/1.0")
        phone = await _login(client, "Phone/2.0")

        sessions = (await client.get("/api/v1/users/me/sessions", headers=_auth(laptop))).json()
        phone_session = next(s for s in sessions if s["user_agent"] == "Phone/2.0")

        revoked = await client.delete(
            f"/api/v1/users/me/sessions/{phone_session['id']}", headers=_auth(laptop)
        )
        phone_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": phone["refresh_token"]}
        )
        laptop_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": laptop["refresh_token"]}
        )
        remaining = (await client.get("/api/v1/users/me/sessions", headers=_auth(laptop))).json()

    assert revoked.status_code == 204
    assert phone_refresh.status_code == 401
    assert laptop_refresh.status_code == 200
    assert [s["user_agent"] for s in remaining] == ["Laptop/1.0"]


async def test_revoking_is_idempotent() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        tokens = await _login(client, "Laptop/1.0")
        await _login(client, "Phone/2.0")
        sessions = (await client.get("/api/v1/users/me/sessions", headers=_auth(tokens))).json()
        target = next(s["id"] for s in sessions if not s["current"])

        first = await client.delete(f"/api/v1/users/me/sessions/{target}", headers=_auth(tokens))
        second = await client.delete(f"/api/v1/users/me/sessions/{target}", headers=_auth(tokens))

    assert first.status_code == second.status_code == 204


async def test_another_users_session_is_not_found() -> None:
    stranger = {**_USER, "email": "stranger@example.com", "phone": "+998904445566"}
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        await client.post("/api/v1/auth/register", json=stranger)
        mine = await _login(client, "Laptop/1.0")
        theirs = (
            await client.post(
                "/api/v1/auth/login",
                json={"email": stranger["email"], "password": stranger["password"]},
            )
        ).json()
        their_sessions = (
            await client.get("/api/v1/users/me/sessions", headers=_auth(theirs))
        ).json()

        foreign = await client.delete(
            f"/api/v1/users/me/sessions/{their_sessions[0]['id']}", headers=_auth(mine)
        )
        unknown = await client.delete(
            f"/api/v1/users/me/sessions/{uuid.uuid4()}", headers=_auth(mine)
        )
        still_theirs = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": theirs["refresh_token"]}
        )

    assert foreign.status_code == 404
    assert unknown.status_code == 404
    assert still_theirs.status_code == 200


async def test_refresh_updates_last_used_and_keeps_the_session_current() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        tokens = await _login(client, "Laptop/1.0")
        before = (await client.get("/api/v1/users/me/sessions", headers=_auth(tokens))).json()[0]

        refreshed = (
            await client.post(
                "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
            )
        ).json()
        after = (await client.get("/api/v1/users/me/sessions", headers=_auth(refreshed))).json()

    assert len(after) == 1
    assert after[0]["id"] == before["id"]
    assert after[0]["current"] is True
    assert after[0]["last_used_at"] >= before["last_used_at"]


async def test_sessions_require_a_token() -> None:
    async with _client() as client:
        response = await client.get("/api/v1/users/me/sessions")

    assert response.status_code == 401
