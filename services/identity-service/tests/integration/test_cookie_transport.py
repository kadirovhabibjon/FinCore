"""ADR-0006: the browser's refresh token travels in an httpOnly cookie.

The cookie is Secure, so the test client (plain http://test) never
replays it from its jar; each test reads Set-Cookie and sends the
Cookie header explicitly, which is also what makes the assertions
about "ignored without the header" meaningful.
"""

import pytest
from httpx import ASGITransport, AsyncClient, Response

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_USER = {
    "email": "lovelace@example.com",
    "phone": "+998907778899",
    "password": "analytical-engine-1843",
    "first_name": "Ada",
    "last_name": "Lovelace",
}
_COOKIE_MODE = {"X-Refresh-Token-Transport": "cookie"}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _refresh_set_cookie(response: Response) -> str:
    headers = [
        value
        for value in response.headers.get_list("set-cookie")
        if value.startswith(f"{settings.refresh_cookie_name}=")
    ]
    assert len(headers) == 1, response.headers.get_list("set-cookie")
    return headers[0]


def _cookie_value(set_cookie: str) -> str:
    return set_cookie.split(";", 1)[0].split("=", 1)[1]


def _cookie_header(value: str) -> dict[str, str]:
    return {"Cookie": f"{settings.refresh_cookie_name}={value}"}


async def _cookie_login(client: AsyncClient) -> Response:
    await client.post("/api/v1/auth/register", json=_USER)
    return await client.post(
        "/api/v1/auth/login",
        json={"email": _USER["email"], "password": _USER["password"]},
        headers=_COOKIE_MODE,
    )


async def test_cookie_login_keeps_the_refresh_token_out_of_the_body() -> None:
    async with _client() as client:
        response = await _cookie_login(client)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"] is None

    set_cookie = _refresh_set_cookie(response)
    attributes = {part.strip().lower() for part in set_cookie.split(";")[1:]}
    assert "httponly" in attributes
    assert "secure" in attributes
    assert "samesite=strict" in attributes
    assert f"path={settings.refresh_cookie_path}" in attributes
    assert any(a.startswith("max-age=") and int(a.split("=")[1]) > 0 for a in attributes)


async def test_body_login_is_unchanged_without_the_header() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": _USER["email"], "password": _USER["password"]},
        )

    assert response.json()["refresh_token"]
    assert response.headers.get_list("set-cookie") == []


async def test_refresh_reads_and_rotates_the_cookie() -> None:
    async with _client() as client:
        login = await _cookie_login(client)
        first = _cookie_value(_refresh_set_cookie(login))

        refreshed = await client.post(
            "/api/v1/auth/refresh", headers={**_COOKIE_MODE, **_cookie_header(first)}
        )
        second = _cookie_value(_refresh_set_cookie(refreshed))
        replayed = await client.post(
            "/api/v1/auth/refresh", headers={**_COOKIE_MODE, **_cookie_header(first)}
        )

    assert refreshed.status_code == 200
    assert refreshed.json()["refresh_token"] is None
    assert second != first
    assert replayed.status_code == 401


async def test_the_cookie_is_ignored_without_the_transport_header() -> None:
    async with _client() as client:
        login = await _cookie_login(client)
        token = _cookie_value(_refresh_set_cookie(login))

        response = await client.post("/api/v1/auth/refresh", headers=_cookie_header(token))

    assert response.status_code == 401


async def test_logout_revokes_the_session_and_clears_the_cookie() -> None:
    async with _client() as client:
        login = await _cookie_login(client)
        token = _cookie_value(_refresh_set_cookie(login))

        logout = await client.post(
            "/api/v1/auth/logout", headers={**_COOKIE_MODE, **_cookie_header(token)}
        )
        after = await client.post(
            "/api/v1/auth/refresh", headers={**_COOKIE_MODE, **_cookie_header(token)}
        )

    assert logout.status_code == 204
    cleared = _refresh_set_cookie(logout).lower()
    assert "max-age=0" in cleared
    assert f"path={settings.refresh_cookie_path}" in cleared
    assert after.status_code == 401


async def test_logout_without_any_token_still_succeeds() -> None:
    async with _client() as client:
        response = await client.post("/api/v1/auth/logout", headers=_COOKIE_MODE)

    assert response.status_code == 204
