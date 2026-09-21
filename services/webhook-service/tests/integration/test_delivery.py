import socket
import uuid
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.db import session as db_session
from app.domain.webhook_delivery import WebhookDelivery, WebhookDeliveryStatus
from app.domain.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus
from app.repositories.webhook_attempt_repository import WebhookAttemptRepository
from app.repositories.webhook_delivery_repository import WebhookDeliveryRepository
from app.repositories.webhook_endpoint_repository import WebhookEndpointRepository
from app.services import ssrf
from app.services.delivery import run_delivery_pass
from app.services.retry import RetryPolicy
from app.services.signing import verify_signature_header

pytestmark = pytest.mark.usefixtures("migrated_database")


@pytest.fixture(autouse=True)
def _fake_public_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every delivery attempt re-runs the real SSRF check
    (app/services/ssrf.py) against `endpoint.url` — see the identical
    fixture in test_webhooks_api.py for why only this one test hostname
    is intercepted, with everything else (including the database's own
    DNS resolution) delegated to the real resolver.
    """
    real_getaddrinfo = socket.getaddrinfo

    def _resolve(host, *args, **kwargs):
        if host == "merchant.example.com":
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]
        return real_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(ssrf.socket, "getaddrinfo", _resolve)


async def _create_endpoint(*, consecutive_failures: int = 0) -> WebhookEndpoint:
    async with db_session.async_session_factory() as session:
        endpoint = WebhookEndpoint(
            merchant_id=uuid.uuid4(),
            owner_user_id=uuid.uuid4(),
            url="https://merchant.example.com/hook",
            secret="test-secret",
            consecutive_failures=consecutive_failures,
        )
        session.add(endpoint)
        await session.commit()
        await session.refresh(endpoint)
        return endpoint


async def _create_delivery(
    endpoint_id: uuid.UUID, *, next_attempt_at: datetime | None = None
) -> WebhookDelivery:
    async with db_session.async_session_factory() as session:
        delivery = WebhookDelivery(
            endpoint_id=endpoint_id,
            event_id=uuid.uuid4(),
            event_type="payment.completed",
            payload={"event": "payment.completed", "payment_id": str(uuid.uuid4())},
            next_attempt_at=next_attempt_at or datetime.now(UTC),
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)
        return delivery


def _merchant_app(*, response_status: int, received: list[Request] | None = None) -> FastAPI:
    fake = FastAPI()

    @fake.post("/hook")
    async def _hook(request: Request) -> JSONResponse:
        if received is not None:
            received.append(request)
        return JSONResponse({"received": True}, status_code=response_status)

    return fake


async def test_successful_delivery_is_marked_succeeded_and_signed_correctly() -> None:
    endpoint = await _create_endpoint()
    delivery = await _create_delivery(endpoint.id)

    captured: list[dict] = []

    fake = FastAPI()

    @fake.post("/hook")
    async def _hook(request: Request) -> JSONResponse:
        body = await request.body()
        captured.append({"headers": dict(request.headers), "body": body})
        return JSONResponse({"ok": True}, status_code=200)

    async with db_session.async_session_factory() as session:
        await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=6),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=10,
            transport=httpx.ASGITransport(app=fake),
        )

    assert len(captured) == 1
    signature_header = captured[0]["headers"]["x-webhook-signature"]
    assert verify_signature_header(
        "test-secret",
        header=signature_header,
        body=captured[0]["body"],
        tolerance_seconds=60,
    )

    async with db_session.async_session_factory() as session:
        refreshed = await WebhookDeliveryRepository(session).get(delivery.id)
        assert refreshed.status == WebhookDeliveryStatus.SUCCEEDED
        assert refreshed.attempts == 1

        attempts = await WebhookAttemptRepository(session).list_for_delivery(delivery.id)
        assert len(attempts) == 1
        assert attempts[0].status_code == 200
        assert attempts[0].latency_ms is not None


async def test_failed_delivery_with_retries_left_is_rescheduled_forward() -> None:
    endpoint = await _create_endpoint()
    delivery = await _create_delivery(endpoint.id)

    async with db_session.async_session_factory() as session:
        await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=6, base_delay_seconds=100.0, jitter_ratio=0.0),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=10,
            transport=httpx.ASGITransport(app=_merchant_app(response_status=500)),
        )

    async with db_session.async_session_factory() as session:
        refreshed = await WebhookDeliveryRepository(session).get(delivery.id)
        assert refreshed.status == WebhookDeliveryStatus.PENDING
        assert refreshed.attempts == 1
        assert refreshed.next_attempt_at > datetime.now(UTC) + timedelta(seconds=50)

        endpoint_after = await WebhookEndpointRepository(session).get(endpoint.id)
        # Not yet terminally failed, so the endpoint's own counter is untouched.
        assert endpoint_after.consecutive_failures == 0


async def test_delivery_is_failed_terminally_after_exhausting_attempts() -> None:
    endpoint = await _create_endpoint()
    delivery = await _create_delivery(endpoint.id)

    async with db_session.async_session_factory() as session:
        await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=1),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=10,
            transport=httpx.ASGITransport(app=_merchant_app(response_status=500)),
        )

    async with db_session.async_session_factory() as session:
        refreshed = await WebhookDeliveryRepository(session).get(delivery.id)
        assert refreshed.status == WebhookDeliveryStatus.FAILED

        endpoint_after = await WebhookEndpointRepository(session).get(endpoint.id)
        assert endpoint_after.consecutive_failures == 1


async def test_endpoint_is_auto_disabled_after_repeated_terminal_failures() -> None:
    endpoint = await _create_endpoint(consecutive_failures=2)
    await _create_delivery(endpoint.id)

    async with db_session.async_session_factory() as session:
        await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=1),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=3,
            transport=httpx.ASGITransport(app=_merchant_app(response_status=500)),
        )

    async with db_session.async_session_factory() as session:
        endpoint_after = await WebhookEndpointRepository(session).get(endpoint.id)
        assert endpoint_after.consecutive_failures == 3
        assert endpoint_after.status == WebhookEndpointStatus.DISABLED


async def test_a_success_resets_the_endpoints_failure_count() -> None:
    endpoint = await _create_endpoint(consecutive_failures=4)
    await _create_delivery(endpoint.id)

    async with db_session.async_session_factory() as session:
        await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=6),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=10,
            transport=httpx.ASGITransport(app=_merchant_app(response_status=200)),
        )

    async with db_session.async_session_factory() as session:
        endpoint_after = await WebhookEndpointRepository(session).get(endpoint.id)
        assert endpoint_after.consecutive_failures == 0


async def test_a_delivery_not_yet_due_is_skipped_this_pass() -> None:
    endpoint = await _create_endpoint()
    future_delivery = await _create_delivery(
        endpoint.id, next_attempt_at=datetime.now(UTC) + timedelta(hours=1)
    )

    async with db_session.async_session_factory() as session:
        attempted = await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=6),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=10,
            transport=httpx.ASGITransport(app=_merchant_app(response_status=200)),
        )

    assert attempted == 0
    async with db_session.async_session_factory() as session:
        refreshed = await WebhookDeliveryRepository(session).get(future_delivery.id)
        assert refreshed.status == WebhookDeliveryStatus.PENDING
        assert refreshed.attempts == 0


async def test_a_delivery_for_an_already_disabled_endpoint_is_failed_without_an_attempt() -> None:
    endpoint = await _create_endpoint()
    delivery = await _create_delivery(endpoint.id)

    async with db_session.async_session_factory() as session:
        # Disabled after the delivery row was queued but before this
        # pass runs — e.g. another delivery in the same batch tripped
        # the auto-disable threshold first.
        await WebhookEndpointRepository(session).record_delivery_failure(
            endpoint.id, disable_after=0
        )
        await session.commit()

    received: list[Request] = []
    fake_app = _merchant_app(response_status=200, received=received)
    async with db_session.async_session_factory() as session:
        await run_delivery_pass(
            session,
            batch_size=10,
            policy=RetryPolicy(max_attempts=6),
            timeout_seconds=2.0,
            disable_after_consecutive_failures=10,
            transport=httpx.ASGITransport(app=fake_app),
        )

    assert received == []
    async with db_session.async_session_factory() as session:
        refreshed = await WebhookDeliveryRepository(session).get(delivery.id)
        assert refreshed.status == WebhookDeliveryStatus.FAILED
