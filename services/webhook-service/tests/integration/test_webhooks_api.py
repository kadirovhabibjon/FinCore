import socket
import uuid

import httpx
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app
from app.services import merchants, ssrf

pytestmark = pytest.mark.usefixtures("migrated_database")


@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registration runs the real SSRF check (app/services/ssrf.py),
    which resolves the endpoint URL's hostname — a made-up hostname like
    "merchant.example.com" has no guaranteed A record, so real DNS can't
    be relied on here. app/services/ssrf.py's own behavior is covered
    directly by tests/unit/test_ssrf.py; here it only needs to resolve
    to *some* public address so registration succeeds.

    `socket.getaddrinfo` is process-global — asyncpg's own connection to
    the test database resolves through it too, so this only intercepts
    the one hostname these tests use and delegates everything else
    (including the database's) to the real resolver.
    """
    real_getaddrinfo = socket.getaddrinfo

    def _resolve(host, *args, **kwargs):
        if host == "merchant.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _resolve)


def _merchant_app(*, merchants_by_id: dict[str, dict]) -> FastAPI:
    fake = FastAPI()

    @fake.get("/internal/v1/merchants/{merchant_id}")
    async def _get_merchant(merchant_id: str) -> JSONResponse:
        merchant = merchants_by_id.get(merchant_id)
        if merchant is None:
            return JSONResponse({"title": "Merchant Not Found"}, status_code=404)
        return JSONResponse(merchant)

    return fake


def _merchant(merchant_id: uuid.UUID, owner_id: uuid.UUID, *, status: str = "ACTIVE") -> dict:
    return {"id": str(merchant_id), "owner_user_id": str(owner_id), "status": status}


def _wire_merchants(monkeypatch: pytest.MonkeyPatch, merchants_by_id: dict[str, dict]) -> None:
    monkeypatch.setattr(
        merchants,
        "merchant_client",
        merchants.MerchantClient(
            base_url="http://payment",
            internal_token=settings.internal_service_token,
            timeout_seconds=2.0,
            transport=httpx.ASGITransport(app=_merchant_app(merchants_by_id=merchants_by_id)),
        ),
    )


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_registering_an_endpoint_returns_its_secret_once(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    token = issue_access_token(owner_id)
    _wire_merchants(
        monkeypatch,
        {str(merchant_id): _merchant(merchant_id, owner_id)},
    )

    async with await _client() as client:
        response = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "https://merchant.example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "ACTIVE"
    assert body["consecutive_failures"] == 0
    assert "secret" in body and len(body["secret"]) > 20


async def test_registering_for_someone_elses_merchant_is_rejected(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    intruder_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    token = issue_access_token(intruder_id)
    _wire_merchants(
        monkeypatch,
        {str(merchant_id): _merchant(merchant_id, owner_id)},
    )

    async with await _client() as client:
        response = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "https://merchant.example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 404


async def test_registering_for_a_suspended_merchant_is_rejected(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    token = issue_access_token(owner_id)
    _wire_merchants(
        monkeypatch,
        {
            str(merchant_id): {
                "id": str(merchant_id),
                "owner_user_id": str(owner_id),
                "status": "SUSPENDED",
            }
        },
    )

    async with await _client() as client:
        response = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "https://merchant.example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 409


async def test_registering_a_private_address_is_rejected_as_ssrf(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    token = issue_access_token(owner_id)
    _wire_merchants(
        monkeypatch,
        {str(merchant_id): _merchant(merchant_id, owner_id)},
    )

    async with await _client() as client:
        response = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "http://127.0.0.1:9999/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 422


async def test_full_lifecycle_list_rotate_enable(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    token = issue_access_token(owner_id)
    _wire_merchants(
        monkeypatch,
        {str(merchant_id): _merchant(merchant_id, owner_id)},
    )

    async with await _client() as client:
        created = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "https://merchant.example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )
        endpoint_id = created.json()["id"]
        original_secret = created.json()["secret"]

        listed = await client.get(
            "/api/v1/webhooks/endpoints", headers={"Authorization": f"Bearer {token}"}
        )
        assert listed.status_code == 200
        assert len(listed.json()) == 1
        assert "secret" not in listed.json()[0]

        got = await client.get(
            f"/api/v1/webhooks/endpoints/{endpoint_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert got.status_code == 200
        assert "secret" not in got.json()

        rotated = await client.post(
            f"/api/v1/webhooks/endpoints/{endpoint_id}/rotate-secret",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert rotated.status_code == 200
        assert rotated.json()["secret"] != original_secret

        enabled = await client.post(
            f"/api/v1/webhooks/endpoints/{endpoint_id}/enable",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert enabled.status_code == 200
        assert enabled.json()["status"] == "ACTIVE"
        assert enabled.json()["consecutive_failures"] == 0


async def test_getting_someone_elses_endpoint_returns_not_found(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    intruder_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    owner_token = issue_access_token(owner_id)
    intruder_token = issue_access_token(intruder_id)
    _wire_merchants(
        monkeypatch,
        {str(merchant_id): _merchant(merchant_id, owner_id)},
    )

    async with await _client() as client:
        created = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "https://merchant.example.com/hook"},
            headers={"Authorization": f"Bearer {owner_token}"},
        )
        endpoint_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/webhooks/endpoints/{endpoint_id}",
            headers={"Authorization": f"Bearer {intruder_token}"},
        )

    assert response.status_code == 404


async def test_deliveries_endpoint_returns_empty_list_for_a_fresh_endpoint(
    issue_access_token, monkeypatch: pytest.MonkeyPatch
) -> None:
    owner_id = uuid.uuid4()
    merchant_id = uuid.uuid4()
    token = issue_access_token(owner_id)
    _wire_merchants(
        monkeypatch,
        {str(merchant_id): _merchant(merchant_id, owner_id)},
    )

    async with await _client() as client:
        created = await client.post(
            "/api/v1/webhooks/endpoints",
            json={"merchant_id": str(merchant_id), "url": "https://merchant.example.com/hook"},
            headers={"Authorization": f"Bearer {token}"},
        )
        endpoint_id = created.json()["id"]

        response = await client.get(
            f"/api/v1/webhooks/endpoints/{endpoint_id}/deliveries",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json() == []
