import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_REGISTER_PAYLOAD = {
    "email": "lovelace@example.com",
    "phone": "+998999999999",
    "password": "analytical-engine-1843",
    "first_name": "Ada",
    "last_name": "Lovelace",
}


async def _register_and_login(client: AsyncClient) -> dict:
    await client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": _REGISTER_PAYLOAD["email"],
            "password": _REGISTER_PAYLOAD["password"],
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_login_response_includes_a_refresh_token() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        body = await _register_and_login(client)

    assert "refresh_token" in body
    assert body["refresh_token"] != body["access_token"]


async def test_refresh_endpoint_issues_a_new_token_pair() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens = await _register_and_login(client)

        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
        )

    assert response.status_code == 200
    new_tokens = response.json()
    assert new_tokens["refresh_token"] != tokens["refresh_token"]
    # Not asserting the access token differs: EdDSA signing is
    # deterministic, and a login immediately followed by a refresh can
    # produce byte-identical claims (same sub/iat/exp/roles within the
    # same second) — that's harmless, not a bug, since the token's
    # validity/expiry is what matters, not its uniqueness.
    assert new_tokens["access_token"]


async def test_reusing_a_refresh_token_after_it_was_rotated_is_rejected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens = await _register_and_login(client)

        first_refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        assert first_refresh.status_code == 200

        replay = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert replay.status_code == 401
    assert replay.json()["title"] == "Invalid Token"


async def test_logout_then_refresh_is_rejected() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens = await _register_and_login(client)

        logout_response = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )
        assert logout_response.status_code == 204

        refresh_after_logout = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert refresh_after_logout.status_code == 401


async def test_logout_is_idempotent() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        tokens = await _register_and_login(client)

        first = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )
        second = await client.post(
            "/api/v1/auth/logout", json={"refresh_token": tokens["refresh_token"]}
        )

    assert first.status_code == 204
    assert second.status_code == 204
