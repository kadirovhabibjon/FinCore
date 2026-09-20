import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")


def _payload(**overrides: object) -> dict:
    payload = {
        "user_id": str(uuid.uuid4()),
        "amount_minor": 100_00,
        "currency": "UZS",
        "operation_type": "TRANSFER",
        "operation_id": str(uuid.uuid4()),
    }
    payload.update(overrides)
    return payload


async def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_a_low_amount_check_returns_allow() -> None:
    async with await _client() as client:
        response = await client.post(
            "/internal/v1/risk-checks",
            json=_payload(),
            headers={"X-Internal-Token": settings.internal_service_token},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "ALLOW"
    assert body["score"] == 0
    assert body["rules_triggered"] == []


async def test_a_large_amount_alone_triggers_the_rule_but_stays_allow() -> None:
    """LARGE_AMOUNT alone is +30 — under the 40-point REVIEW threshold
    (spec Section 12's worked example), so triggering just this one rule
    is still ALLOW. REVIEW/BLOCK need more than one rule to trigger
    together (covered by the rule-combination tests in test_rules.py).
    """
    async with await _client() as client:
        response = await client.post(
            "/internal/v1/risk-checks",
            json=_payload(amount_minor=settings.large_amount_threshold_minor + 1),
            headers={"X-Internal-Token": settings.internal_service_token},
        )

    assert response.status_code == 201
    body = response.json()
    assert body["decision"] == "ALLOW"
    assert body["score"] == 30
    assert body["rules_triggered"] == ["LARGE_AMOUNT"]


async def test_repeating_the_same_operation_replays_the_stored_result() -> None:
    payload = _payload()
    async with await _client() as client:
        first = await client.post(
            "/internal/v1/risk-checks",
            json=payload,
            headers={"X-Internal-Token": settings.internal_service_token},
        )
        second = await client.post(
            "/internal/v1/risk-checks",
            json=payload,
            headers={"X-Internal-Token": settings.internal_service_token},
        )

    assert first.json()["id"] == second.json()["id"]


async def test_a_missing_internal_token_is_rejected() -> None:
    async with await _client() as client:
        response = await client.post("/internal/v1/risk-checks", json=_payload())

    assert response.status_code in (401, 403, 422)


async def test_a_wrong_internal_token_is_rejected() -> None:
    async with await _client() as client:
        response = await client.post(
            "/internal/v1/risk-checks",
            json=_payload(),
            headers={"X-Internal-Token": "wrong-token"},
        )

    assert response.status_code == 403


# Gateway unreachability (spec Section 19: /internal/* never routed
# through the gateway) isn't testable here — the gateway is a separate
# nginx process, not something an ASGI-transport test against this app
# can exercise. Verified instead against the live docker-compose stack;
# see the "Run it" section of the README.