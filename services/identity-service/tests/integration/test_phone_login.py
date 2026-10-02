import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_USER = {
    "email": "babbage@example.com",
    "phone": "+998 90 123-45-67",
    "password": "difference-engine-1822",
    "first_name": "Charles",
    "last_name": "Babbage",
}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_the_phone_is_stored_in_one_canonical_form() -> None:
    async with _client() as client:
        registered = await client.post("/api/v1/auth/register", json=_USER)

    assert registered.status_code == 201
    assert registered.json()["phone"] == "+998901234567"


@pytest.mark.parametrize(
    "typed", ["+998901234567", "998901234567", "90 123 45 67", "901234567", "+998 (90) 123-45-67"]
)
async def test_sign_in_with_the_phone_however_it_is_typed(typed: str) -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        response = await client.post(
            "/api/v1/auth/login", json={"phone": typed, "password": _USER["password"]}
        )

    assert response.status_code == 200
    assert response.json()["access_token"]


async def test_email_sign_in_still_works() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        response = await client.post(
            "/api/v1/auth/login",
            json={"email": "Babbage@Example.com", "password": _USER["password"]},
        )

    assert response.status_code == 200


async def test_wrong_password_or_unknown_phone_get_the_same_answer() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        wrong = await client.post(
            "/api/v1/auth/login", json={"phone": "901234567", "password": "not-the-password"}
        )
        unknown = await client.post(
            "/api/v1/auth/login", json={"phone": "+998 99 999 99 99", "password": "whatever-123"}
        )

    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["title"] == unknown.json()["title"] == "Invalid Credentials"


@pytest.mark.parametrize(
    "body",
    [
        {"password": "x"},  # neither
        {"email": "babbage@example.com", "phone": "901234567", "password": "x"},  # both
        {"phone": "12345", "password": "x"},  # not a phone number
    ],
)
async def test_malformed_sign_in_requests_are_rejected(body: dict) -> None:
    async with _client() as client:
        response = await client.post("/api/v1/auth/login", json=body)

    assert response.status_code == 422


async def test_the_same_number_written_differently_cant_register_twice() -> None:
    async with _client() as client:
        await client.post("/api/v1/auth/register", json=_USER)
        again = await client.post(
            "/api/v1/auth/register",
            json={**_USER, "email": "other@example.com", "phone": "901234567"},
        )

    assert again.status_code == 409
    assert again.json()["title"] == "Phone Already Registered"
