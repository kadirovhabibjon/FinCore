import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


async def test_register_endpoint_returns_created_user() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "Test.User@Example.com",
                "phone": "+998933333333",
                "password": "a-reasonably-strong-password",
                "first_name": "Test",
                "last_name": "User",
            },
        )

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "test.user@example.com"  # normalized by the schema
    assert "password" not in body
    assert "password_hash" not in body


async def test_register_endpoint_rejects_duplicate_email_with_rfc7807() -> None:
    transport = ASGITransport(app=app)
    payload = {
        "email": "dup@example.com",
        "phone": "+998944444444",
        "password": "a-reasonably-strong-password",
        "first_name": "Dup",
        "last_name": "One",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post("/api/v1/auth/register", json=payload)
        payload["phone"] = "+998955555555"
        second = await client.post("/api/v1/auth/register", json=payload)

    assert first.status_code == 201
    assert second.status_code == 409
    body = second.json()
    assert body["title"] == "Email Already Registered"
    assert body["status"] == 409


async def test_register_endpoint_rejects_short_password_with_rfc7807() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "short@example.com",
                "phone": "+998966666666",
                "password": "short",
                "first_name": "Short",
                "last_name": "Pw",
            },
        )

    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Validation Error"
