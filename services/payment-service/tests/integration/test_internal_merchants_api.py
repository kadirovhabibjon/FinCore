import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_internal_lookup_returns_owner_and_status(issue_access_token) -> None:
    owner_id = uuid.uuid4()
    token = issue_access_token(owner_id)

    async with await _client() as client:
        created = await client.post(
            "/api/v1/merchants",
            json={"name": "Owner's Shop"},
            headers={"Authorization": f"Bearer {token}"},
        )
        merchant_id = created.json()["id"]

        response = await client.get(
            f"/internal/v1/merchants/{merchant_id}",
            headers={"X-Internal-Token": "test-only-internal-token"},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == merchant_id
    assert body["owner_user_id"] == str(owner_id)
    assert body["status"] == "ACTIVE"


async def test_internal_lookup_rejects_missing_or_wrong_token() -> None:
    async with await _client() as client:
        response = await client.get(f"/internal/v1/merchants/{uuid.uuid4()}")
    assert response.status_code == 422  # missing required header

    async with await _client() as client:
        response = await client.get(
            f"/internal/v1/merchants/{uuid.uuid4()}",
            headers={"X-Internal-Token": "wrong-token"},
        )
    assert response.status_code == 403


async def test_internal_lookup_unknown_merchant_returns_404() -> None:
    async with await _client() as client:
        response = await client.get(
            f"/internal/v1/merchants/{uuid.uuid4()}",
            headers={"X-Internal-Token": "test-only-internal-token"},
        )
    assert response.status_code == 404
