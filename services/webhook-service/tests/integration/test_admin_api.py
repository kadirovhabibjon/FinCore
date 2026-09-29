import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.db import session as db_session
from app.domain.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _endpoint(owner_id: uuid.UUID, merchant_id: uuid.UUID) -> WebhookEndpoint:
    # Inserted directly: registration (merchant lookup, SSRF check) is
    # covered by test_webhooks_api.py and isn't what's under test here.
    async with db_session.async_session_factory() as session:
        endpoint = WebhookEndpoint(
            merchant_id=merchant_id,
            owner_user_id=owner_id,
            url="https://merchant.example.com/hooks",
            secret="s3cret",
        )
        session.add(endpoint)
        await session.commit()
        await session.refresh(endpoint)
        return endpoint


async def test_staff_list_every_endpoint_without_secrets(issue_access_token) -> None:
    owner_a, owner_b = uuid.uuid4(), uuid.uuid4()
    merchant_b = uuid.uuid4()
    first = await _endpoint(owner_a, uuid.uuid4())
    second = await _endpoint(owner_b, merchant_b)
    support = issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"])

    async with _client() as client:
        everything = await client.get("/api/v1/admin/webhooks/endpoints", headers=_auth(support))
        by_merchant = await client.get(
            "/api/v1/admin/webhooks/endpoints",
            params={"merchant_id": str(merchant_b)},
            headers=_auth(support),
        )
        history = await client.get(
            f"/api/v1/admin/webhooks/endpoints/{first.id}/deliveries", headers=_auth(support)
        )

    body = everything.json()
    assert [e["id"] for e in body] == [str(second.id), str(first.id)]
    assert [e["owner_user_id"] for e in body] == [str(owner_b), str(owner_a)]
    assert all("secret" not in e for e in body)
    assert [e["id"] for e in by_merchant.json()] == [str(second.id)]
    assert history.status_code == 200
    assert history.json() == []


async def test_plain_users_cannot_reach_the_admin_api(issue_access_token) -> None:
    owner = uuid.uuid4()
    endpoint = await _endpoint(owner, uuid.uuid4())
    token = issue_access_token(owner)

    async with _client() as client:
        listing = await client.get("/api/v1/admin/webhooks/endpoints", headers=_auth(token))
        disable = await client.post(
            f"/api/v1/admin/webhooks/endpoints/{endpoint.id}/disable", headers=_auth(token)
        )

    assert listing.status_code == 403
    assert disable.status_code == 403


async def test_only_admins_disable_and_the_owner_sees_it(issue_access_token) -> None:
    owner = uuid.uuid4()
    endpoint = await _endpoint(owner, uuid.uuid4())
    support = issue_access_token(uuid.uuid4(), ["USER", "SUPPORT"])
    admin = issue_access_token(uuid.uuid4(), ["USER", "ADMIN"])
    owner_token = issue_access_token(owner)

    async with _client() as client:
        by_support = await client.post(
            f"/api/v1/admin/webhooks/endpoints/{endpoint.id}/disable", headers=_auth(support)
        )
        disabled = await client.post(
            f"/api/v1/admin/webhooks/endpoints/{endpoint.id}/disable", headers=_auth(admin)
        )
        only_disabled = await client.get(
            "/api/v1/admin/webhooks/endpoints",
            params={"status": "DISABLED"},
            headers=_auth(admin),
        )
        owner_view = await client.get(
            f"/api/v1/webhooks/endpoints/{endpoint.id}", headers=_auth(owner_token)
        )
        enabled = await client.post(
            f"/api/v1/admin/webhooks/endpoints/{endpoint.id}/enable", headers=_auth(admin)
        )
        unknown = await client.post(
            f"/api/v1/admin/webhooks/endpoints/{uuid.uuid4()}/disable", headers=_auth(admin)
        )

    assert by_support.status_code == 403
    assert disabled.json()["status"] == WebhookEndpointStatus.DISABLED
    assert [e["id"] for e in only_disabled.json()] == [str(endpoint.id)]
    assert owner_view.json()["status"] == WebhookEndpointStatus.DISABLED
    assert enabled.json()["status"] == WebhookEndpointStatus.ACTIVE
    assert unknown.status_code == 404
