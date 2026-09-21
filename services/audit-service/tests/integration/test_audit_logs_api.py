import uuid
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.db import session as db_session
from app.domain.audit_log import AuditLog
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _insert(actor_id: uuid.UUID, action: str, resource_type: str, resource_id: str) -> None:
    async with db_session.async_session_factory() as session:
        session.add(
            AuditLog(
                event_id=uuid.uuid4(),
                actor_id=actor_id,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                result="COMPLETED",
                details={},
                occurred_at=datetime.now(UTC),
            )
        )
        await session.commit()


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


_HEADERS = {"X-Internal-Token": settings.internal_service_token}


async def test_search_without_filters_returns_everything_newest_first() -> None:
    actor = uuid.uuid4()
    await _insert(actor, "TRANSFER_COMPLETED", "Transfer", "t-1")
    await _insert(actor, "PAYMENT_COMPLETED", "Payment", "p-1")

    async with await _client() as client:
        response = await client.get("/internal/v1/audit-logs", headers=_HEADERS)

    assert response.status_code == 200
    assert len(response.json()) == 2


async def test_search_filters_by_actor_id() -> None:
    actor_a = uuid.uuid4()
    actor_b = uuid.uuid4()
    await _insert(actor_a, "TRANSFER_COMPLETED", "Transfer", "t-2")
    await _insert(actor_b, "TRANSFER_COMPLETED", "Transfer", "t-3")

    async with await _client() as client:
        response = await client.get(
            "/internal/v1/audit-logs", params={"actor_id": str(actor_a)}, headers=_HEADERS
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["actor_id"] == str(actor_a)


async def test_search_filters_by_resource_type_and_action() -> None:
    actor = uuid.uuid4()
    await _insert(actor, "PAYMENT_FAILED", "Payment", "p-2")
    await _insert(actor, "PAYMENT_COMPLETED", "Payment", "p-3")

    async with await _client() as client:
        response = await client.get(
            "/internal/v1/audit-logs",
            params={"resource_type": "Payment", "action": "PAYMENT_FAILED"},
            headers={"X-Internal-Token": settings.internal_service_token},
        )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["action"] == "PAYMENT_FAILED"


async def test_search_without_a_valid_internal_token_is_rejected() -> None:
    async with await _client() as client:
        response = await client.get("/internal/v1/audit-logs")
    assert response.status_code == 422

    async with await _client() as client:
        response = await client.get(
            "/internal/v1/audit-logs", headers={"X-Internal-Token": "wrong-token"}
        )
    assert response.status_code == 403
