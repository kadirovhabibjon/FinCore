"""Staff look at one customer's wallets (the admin console)."""

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_staff_see_a_customers_wallets_as_the_customer_does(issue_access_token) -> None:
    customer_id = uuid.uuid4()
    customer = {"Authorization": f"Bearer {issue_access_token(customer_id)}"}
    support = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4(), ['USER', 'SUPPORT'])}"}
    admin = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4(), ['ADMIN'])}"}

    async with _client() as client:
        await client.post("/api/v1/wallets", json={"currency": "UZS"}, headers=customer)
        usd = (
            await client.post("/api/v1/wallets", json={"currency": "USD"}, headers=customer)
        ).json()
        await client.patch(
            f"/api/v1/wallets/{usd['id']}", json={"name": "Travel"}, headers=customer
        )
        await client.post(f"/api/v1/wallets/{usd['id']}/block", headers=customer)
        # Someone else's wallet must not appear.
        other = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4())}"}
        await client.post("/api/v1/wallets", json={"currency": "UZS"}, headers=other)

        own_view = (await client.get("/api/v1/wallets", headers=customer)).json()
        url, params = "/api/v1/admin/wallets", {"user_id": str(customer_id)}
        seen = await client.get(url, params=params, headers=support)
        seen_by_admin = await client.get(url, params=params, headers=admin)
        nobody = await client.get(url, params={"user_id": str(uuid.uuid4())}, headers=support)
        as_customer = await client.get(url, params=params, headers=customer)
        anonymous = await client.get(url, params=params)
        no_user = await client.get(url, headers=support)

    assert seen.status_code == 200
    assert seen.json() == seen_by_admin.json() == own_view
    assert [(w["currency"], w["name"], w["blocked"], w["is_primary"]) for w in seen.json()] == [
        ("UZS", None, False, True),
        ("USD", "Travel", True, False),
    ]
    assert nobody.json() == []
    assert as_customer.status_code == 403
    assert as_customer.json()["title"] == "Insufficient Role"
    assert anonymous.status_code == 401
    assert no_user.status_code == 422


@pytest.mark.parametrize("method", ["post", "patch", "put", "delete"])
async def test_staff_can_only_look(issue_access_token, method: str) -> None:
    admin = {"Authorization": f"Bearer {issue_access_token(uuid.uuid4(), ['ADMIN'])}"}

    async with _client() as client:
        response = await client.request(
            method, "/api/v1/admin/wallets", params={"user_id": str(uuid.uuid4())}, headers=admin
        )

    assert response.status_code == 405
