import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_TOKEN = "internal-test-token"


@pytest.fixture(autouse=True)
def _internal_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "internal_service_token", _TOKEN)


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _register(client: AsyncClient) -> dict:
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": f"{uuid.uuid4().hex[:10]}@example.com",
            "phone": f"+99890{uuid.uuid4().int % 10**7:07d}",
            "password": "correct-horse-battery",
            "first_name": "Aziza",
            "last_name": "Karimova",
        },
    )
    return response.json()


async def test_returns_a_users_name_and_status_and_nothing_else() -> None:
    async with _client() as client:
        user = await _register(client)
        response = await client.get(
            f"/internal/v1/users/{user['id']}", headers={"X-Internal-Token": _TOKEN}
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": user["id"],
        "first_name": "Aziza",
        "last_name": "Karimova",
        "status": "ACTIVE",
    }


async def test_an_unknown_user_is_404() -> None:
    async with _client() as client:
        response = await client.get(
            f"/internal/v1/users/{uuid.uuid4()}", headers={"X-Internal-Token": _TOKEN}
        )

    assert response.status_code == 404


async def test_needs_the_internal_token() -> None:
    async with _client() as client:
        user = await _register(client)
        missing = await client.get(f"/internal/v1/users/{user['id']}")
        wrong = await client.get(
            f"/internal/v1/users/{user['id']}", headers={"X-Internal-Token": "wrong"}
        )

    assert missing.status_code == 422
    assert wrong.status_code == 403


async def test_with_no_token_configured_every_request_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "internal_service_token", "")
    async with _client() as client:
        user = await _register(client)
        response = await client.get(
            f"/internal/v1/users/{user['id']}", headers={"X-Internal-Token": ""}
        )

    assert response.status_code == 403


async def test_finds_a_user_by_phone_however_the_number_is_typed() -> None:
    async with _client() as client:
        user = await _register(client)
        phone = user["phone"]  # "+99890XXXXXXX"
        typed = [phone, phone[1:], phone[4:], f"{phone[:4]} {phone[4:6]} {phone[6:9]}-{phone[9:]}"]
        responses = [
            await client.get(
                "/internal/v1/users/by-phone",
                params={"phone": value},
                headers={"X-Internal-Token": _TOKEN},
            )
            for value in typed
        ]

    assert [response.status_code for response in responses] == [200] * len(typed)
    assert all(response.json()["id"] == user["id"] for response in responses)
    # Still no email, phone or roles in what another service is told.
    assert set(responses[0].json()) == {"id", "first_name", "last_name", "status"}


async def test_by_phone_tells_an_unknown_number_from_a_malformed_one() -> None:
    async with _client() as client:
        unknown = await client.get(
            "/internal/v1/users/by-phone",
            params={"phone": "+998900000000"},
            headers={"X-Internal-Token": _TOKEN},
        )
        malformed = await client.get(
            "/internal/v1/users/by-phone",
            params={"phone": "12345"},
            headers={"X-Internal-Token": _TOKEN},
        )
        no_token = await client.get(
            "/internal/v1/users/by-phone", params={"phone": "+998900000000"}
        )
        wrong_token = await client.get(
            "/internal/v1/users/by-phone",
            params={"phone": "+998900000000"},
            headers={"X-Internal-Token": "nope"},
        )

    assert unknown.status_code == 404 and unknown.json()["title"] == "User Not Found"
    assert malformed.status_code == 422 and malformed.json()["title"] == "Invalid Phone Number"
    assert no_token.status_code == 422
    assert wrong_token.status_code == 403
