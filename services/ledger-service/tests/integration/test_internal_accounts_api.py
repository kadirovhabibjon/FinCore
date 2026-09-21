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
