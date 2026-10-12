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


async def test_a_customer_about_to_pay_sees_the_merchants_name_and_nothing_else(
    issue_access_token,
) -> None:
    from sqlalchemy import update

    from app.db import session as db_session
    from app.domain.merchant import Merchant, MerchantStatus
    from app.services import billers

    owner = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    payer = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
    beeline = billers.find("beeline")
    assert beeline is not None

    async with await _client() as client:
        shop = (
            await client.post("/api/v1/merchants", json={"name": "Chorsu Coffee"}, headers=owner)
        ).json()
        url = f"/api/v1/merchants/{shop['id']}/public"
        seen = await client.get(url, headers=payer)
        # The owner's own view stays the owner's.
        private = await client.get(f"/api/v1/merchants/{shop['id']}", headers=payer)
        anonymous = await client.get(url)
        unknown = await client.get(f"/api/v1/merchants/{uuid.uuid4()}/public", headers=payer)
        provider = await client.get(
            f"/api/v1/merchants/{beeline.merchant_id}/public", headers=payer
        )
        async with db_session.async_session_factory() as session:
            await session.execute(
                update(Merchant)
                .where(Merchant.id == uuid.UUID(shop["id"]))
                .values(status=MerchantStatus.SUSPENDED)
            )
            await session.commit()
        suspended = await client.get(url, headers=payer)

    assert seen.status_code == 200
    assert seen.json() == {"id": shop["id"], "name": "Chorsu Coffee", "active": True}
    assert private.status_code == 404
    assert anonymous.status_code == 401
    assert unknown.status_code == 404 and unknown.json()["title"] == "Merchant Not Found"
    # Providers are paid with an account, through /api/v1/services.
    assert provider.status_code == 404
    assert suspended.json()["active"] is False
