import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_creating_a_merchant_returns_it_owned_by_the_caller(issue_access_token) -> None:
    token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        response = await client.post(
            "/api/v1/merchants",
            json={"name": "Test Shop"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Test Shop"
    assert body["status"] == "ACTIVE"


async def test_listing_merchants_only_returns_the_callers_own(issue_access_token) -> None:
    owner_token = issue_access_token(uuid.uuid4())
    other_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        await client.post(
            "/api/v1/merchants",
            json={"name": "Owner's Shop"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )

        response = await client.get(
            "/api/v1/merchants", headers={"Authorization": f"Bearer {other_token}"}
        )

    assert response.status_code == 200
    assert response.json() == []


async def test_getting_someone_elses_merchant_returns_not_found(issue_access_token) -> None:
    owner_token = issue_access_token(uuid.uuid4())
    intruder_token = issue_access_token(uuid.uuid4())

    async with await _client() as client:
        created = await client.post(
            "/api/v1/merchants",
            json={"name": "Owner's Shop"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        merchant_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/merchants/{merchant_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404
