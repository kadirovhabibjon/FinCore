import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_HEADERS = {"X-Internal-Token": settings.internal_service_token}


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_looks_up_a_seeded_system_account_by_kind_and_currency() -> None:
    async with await _client() as client:
        response = await client.get(
            "/internal/v1/accounts/system",
            params={"kind": "MERCHANT_SETTLEMENT", "currency": "UZS"},
            headers=_HEADERS,
        )

    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "MERCHANT_SETTLEMENT"
    assert body["currency"] == "UZS"


async def test_a_currency_with_no_seeded_account_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(
            "/internal/v1/accounts/system",
            params={"kind": "MERCHANT_SETTLEMENT", "currency": "EUR"},
            headers=_HEADERS,
        )

    assert response.status_code == 404


async def test_requires_the_internal_token_header() -> None:
    async with await _client() as client:
        response = await client.get(
            "/internal/v1/accounts/system",
            params={"kind": "MERCHANT_SETTLEMENT", "currency": "UZS"},
        )

    assert response.status_code == 422


async def test_finds_the_wallet_a_card_number_belongs_to(issue_access_token) -> None:
    owner = uuid.uuid4()
    async with await _client() as client:
        wallet = (
            await client.post(
                "/api/v1/wallets",
                json={"currency": "USD"},
                headers={"Authorization": f"Bearer {issue_access_token(owner)}"},
            )
        ).json()
        response = await client.get(
            "/internal/v1/accounts/wallet-by-card",
            params={"card_number": wallet["card_number"]},
            headers=_HEADERS,
        )

    assert response.status_code == 200
    assert response.json() == {
        "id": wallet["id"],
        "owner_user_id": str(owner),
        "card_number": wallet["card_number"],
        "currency": "USD",
        "status": "ACTIVE",
    }


async def test_an_unknown_or_malformed_card_number_finds_nothing() -> None:
    async with await _client() as client:
        unknown = await client.get(
            "/internal/v1/accounts/wallet-by-card",
            params={"card_number": "9955000000000000"},
            headers=_HEADERS,
        )
        malformed = await client.get(
            "/internal/v1/accounts/wallet-by-card",
            params={"card_number": "9955-not-a-number"},
            headers=_HEADERS,
        )

    assert unknown.status_code == 404
    assert malformed.status_code == 422


async def test_card_lookup_requires_the_internal_token() -> None:
    async with await _client() as client:
        response = await client.get(
            "/internal/v1/accounts/wallet-by-card",
            params={"card_number": "9955000000000000"},
            headers={"X-Internal-Token": "wrong"},
        )

    assert response.status_code == 403


async def test_finds_a_wallets_owner_by_wallet_id(issue_access_token) -> None:
    owner = uuid.uuid4()
    async with await _client() as client:
        wallet = (
            await client.post(
                "/api/v1/wallets",
                json={"currency": "UZS"},
                headers={"Authorization": f"Bearer {issue_access_token(owner)}"},
            )
        ).json()
        found = await client.get(f"/internal/v1/accounts/wallets/{wallet['id']}", headers=_HEADERS)
        unknown = await client.get(
            f"/internal/v1/accounts/wallets/{uuid.uuid4()}", headers=_HEADERS
        )
        unauthorized = await client.get(
            f"/internal/v1/accounts/wallets/{wallet['id']}", headers={"X-Internal-Token": "wrong"}
        )

    assert found.status_code == 200
    assert found.json()["owner_user_id"] == str(owner)
    assert found.json()["card_number"] == wallet["card_number"]
    assert unknown.status_code == 404
    assert unauthorized.status_code == 403
