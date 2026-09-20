import uuid

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.domain.transfer import FraudDecision
from app.services.fraud import FraudClient


def _fake_fraud_service(decision: str, status_code: int = 200) -> httpx.ASGITransport:
    app = FastAPI()

    @app.post("/internal/v1/risk-checks")
    async def _risk_check() -> JSONResponse:
        return JSONResponse({"decision": decision, "score": 10}, status_code=status_code)

    return httpx.ASGITransport(app=app)


def _client(transport: httpx.ASGITransport | None = None, **overrides) -> FraudClient:
    defaults = {
        "base_url": "http://fraud",
        "internal_token": "test-token",
        "timeout_seconds": 0.2,
        "fail_open_limit_minor": 100_000_00,
    }
    defaults.update(overrides)
    return FraudClient(transport=transport, **defaults)


async def test_check_returns_allow_when_fraud_service_allows() -> None:
    client = _client(transport=_fake_fraud_service("ALLOW"))

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=5_000_00,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.decision == FraudDecision.ALLOW
    assert result.fail_open is False


async def test_check_returns_block_when_fraud_service_blocks() -> None:
    client = _client(transport=_fake_fraud_service("BLOCK"))

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=5_000_00,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.decision == FraudDecision.BLOCK
    assert result.fail_open is False


async def test_check_returns_review_when_fraud_service_says_review() -> None:
    client = _client(transport=_fake_fraud_service("REVIEW"))

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=5_000_00,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.decision == FraudDecision.REVIEW


async def test_a_5xx_response_triggers_the_failure_policy() -> None:
    client = _client(transport=_fake_fraud_service("ALLOW", status_code=500))

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=5_000_00,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.fail_open is True
    assert result.decision == FraudDecision.ALLOW  # amount is under the limit


async def test_an_unreachable_fraud_service_triggers_the_failure_policy() -> None:
    """No fake transport here at all: a real connection attempt against a
    port nothing is listening on — genuine network-level unavailability
    (fraud-service down, network partition, etc.), not a mocked
    exception.
    """
    client = _client(
        transport=None, base_url="http://127.0.0.1:59999", timeout_seconds=0.2
    )

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=5_000_00,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.fail_open is True


async def test_failure_policy_allows_amounts_at_or_under_the_limit() -> None:
    client = _client(
        transport=None, base_url="http://127.0.0.1:59999", fail_open_limit_minor=100_000_00
    )

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=100_000_00,  # exactly at the limit
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.decision == FraudDecision.ALLOW
    assert result.fail_open is True


async def test_failure_policy_reviews_amounts_over_the_limit() -> None:
    client = _client(
        transport=None, base_url="http://127.0.0.1:59999", fail_open_limit_minor=100_000_00
    )

    result = await client.check(
        user_id=uuid.uuid4(),
        amount_minor=100_000_01,
        currency="UZS",
        operation_type="TRANSFER",
        operation_id=uuid.uuid4(),
    )

    assert result.decision == FraudDecision.REVIEW
    assert result.fail_open is True


async def test_a_4xx_response_is_not_swallowed_by_the_failure_policy() -> None:
    """A 4xx means *our own* request was malformed — a real bug, not
    fraud-service being unavailable. The failure policy must not hide
    that by silently returning ALLOW/REVIEW.
    """
    client = _client(transport=_fake_fraud_service("ALLOW", status_code=400))

    try:
        await client.check(
            user_id=uuid.uuid4(),
            amount_minor=5_000_00,
            currency="UZS",
            operation_type="TRANSFER",
            operation_id=uuid.uuid4(),
        )
        raise AssertionError("expected an HTTPStatusError to propagate")
    except httpx.HTTPStatusError:
        pass
