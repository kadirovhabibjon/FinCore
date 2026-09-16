import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_REGISTER_PAYLOAD = {
    "email": "curie@example.com",
    "phone": "+998977777777",
    "password": "radioactive-decay-1898",
    "first_name": "Marie",
    "last_name": "Curie",
}


async def _register_and_login(client: AsyncClient) -> str:
    await client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": _REGISTER_PAYLOAD["email"],
            "password": _REGISTER_PAYLOAD["password"],
        },
    )
    assert response.status_code == 200
    return response.json()["access_token"]


async def test_login_returns_a_bearer_token_for_correct_credentials() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)

        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": _REGISTER_PAYLOAD["email"],
                "password": _REGISTER_PAYLOAD["password"],
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] > 0
    assert len(body["access_token"].split(".")) == 3  # header.payload.signature


async def test_login_rejects_wrong_password_with_rfc7807() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/auth/register", json=_REGISTER_PAYLOAD)

        response = await client.post(
            "/api/v1/auth/login",
            json={"email": _REGISTER_PAYLOAD["email"], "password": "wrong"},
        )

    assert response.status_code == 401
    assert response.json()["title"] == "Invalid Credentials"


async def test_me_returns_the_authenticated_users_profile() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        token = await _register_and_login(client)

        response = await client.get(
            "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
        )

    assert response.status_code == 200
    body = response.json()
    assert body["email"] == _REGISTER_PAYLOAD["email"]
    assert "password" not in body
    assert "password_hash" not in body


async def test_me_rejects_missing_token() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/users/me")

    assert response.status_code == 401
    assert response.json()["title"] == "Invalid Token"


async def test_me_rejects_a_malformed_token() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/users/me",
            headers={"Authorization": "Bearer not-a-real-token"},
        )

    assert response.status_code == 401
    assert response.json()["title"] == "Invalid Token"
