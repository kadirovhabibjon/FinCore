import json
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidWebhookUrlError
from app.core.metrics import DELIVERIES_TERMINALLY_FAILED_TOTAL
from app.domain.webhook_attempt import WebhookAttempt
from app.domain.webhook_delivery import WebhookDelivery
from app.domain.webhook_endpoint import WebhookEndpoint
from app.repositories.webhook_delivery_repository import WebhookDeliveryRepository
from app.repositories.webhook_endpoint_repository import WebhookEndpointRepository
from app.services.retry import RetryPolicy
from app.services.signing import build_signature_header, current_timestamp
from app.services.ssrf import assert_safe_url

logger = logging.getLogger(__name__)


async def attempt_delivery(
    session: AsyncSession,
    delivery: WebhookDelivery,
    endpoint: WebhookEndpoint,
    *,
    policy: RetryPolicy,
    timeout_seconds: float,
    disable_after_consecutive_failures: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> None:
    """Makes exactly one signed HTTP attempt at `delivery`, records it
    (spec Section 17: "delivery history — every attempt with status code
    and latency"), and updates the delivery's and endpoint's state.

    The SSRF check (app/services/ssrf.py) runs fresh on every attempt,
    not only at registration time — DNS can change between when an
    endpoint was registered and when this fires (see that module's own
    docstring).
    """
    attempt_number = delivery.attempts + 1
    body = json.dumps(delivery.payload, separators=(",", ":")).encode("utf-8")
    timestamp = current_timestamp()
    signature = build_signature_header(endpoint.secret, timestamp=timestamp, body=body)

    status_code: int | None = None
    latency_ms: int | None = None
    error: str | None = None

    try:
        await assert_safe_url(endpoint.url)
        start = time.monotonic()
        async with httpx.AsyncClient(timeout=timeout_seconds, transport=transport) as client:
            response = await client.post(
                endpoint.url,
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Webhook-Id": str(delivery.event_id),
                    "X-Webhook-Signature": signature,
                    "X-Webhook-Timestamp": str(timestamp),
                },
            )
        latency_ms = int((time.monotonic() - start) * 1000)
        status_code = response.status_code
        success = 200 <= response.status_code < 300
        if not success:
            error = f"unexpected status code {response.status_code}"
    except InvalidWebhookUrlError as exc:
        success = False
        error = str(exc)
    except httpx.RequestError as exc:
        success = False
        error = str(exc)

    session.add(
        WebhookAttempt(
            delivery_id=delivery.id,
            attempt_number=attempt_number,
            status_code=status_code,
            latency_ms=latency_ms,
            error=error,
        )
    )

    delivery_repository = WebhookDeliveryRepository(session)
    endpoint_repository = WebhookEndpointRepository(session)

    if success:
        await delivery_repository.mark_succeeded(delivery.id, attempts=attempt_number)
        await endpoint_repository.record_delivery_success(endpoint.id)
        await session.commit()
        return

    logger.warning(
        "webhook delivery %s to endpoint %s failed on attempt %d: %s",
        delivery.id,
        endpoint.id,
        attempt_number,
        error,
    )

    if attempt_number >= policy.max_attempts:
        await delivery_repository.mark_failed(
            delivery.id, attempts=attempt_number, last_error=error or "unknown error"
        )
        DELIVERIES_TERMINALLY_FAILED_TOTAL.inc()
        await endpoint_repository.record_delivery_failure(
            endpoint.id, disable_after=disable_after_consecutive_failures
        )
    else:
        next_attempt_at = datetime.now(UTC) + timedelta(
            seconds=policy.delay_seconds(attempt_number + 1)
        )
        await delivery_repository.reschedule(
            delivery.id,
            attempts=attempt_number,
            next_attempt_at=next_attempt_at,
            last_error=error or "unknown error",
        )
    await session.commit()


async def run_delivery_pass(
    session: AsyncSession,
    *,
    batch_size: int,
    policy: RetryPolicy,
    timeout_seconds: float,
    disable_after_consecutive_failures: int,
    transport: httpx.AsyncBaseTransport | None = None,
) -> int:
    """One pass of the delivery worker loop (app/main.py): attempts
    every due delivery, oldest first. A delivery whose endpoint was
    disabled since it was queued (e.g. by an earlier delivery in this
    same pass) is failed outright rather than attempted — no point
    signing and sending a request the merchant has effectively opted
    out of receiving.
    """
    delivery_repository = WebhookDeliveryRepository(session)
    endpoint_repository = WebhookEndpointRepository(session)
    due = await delivery_repository.list_due(now=datetime.now(UTC), limit=batch_size)

    attempted = 0
    for delivery in due:
        endpoint = await endpoint_repository.get(delivery.endpoint_id)
        if endpoint is None or endpoint.status.value != "ACTIVE":
            await delivery_repository.mark_failed(
                delivery.id, attempts=delivery.attempts, last_error="endpoint disabled"
            )
            DELIVERIES_TERMINALLY_FAILED_TOTAL.inc()
            await session.commit()
            continue

        await attempt_delivery(
            session,
            delivery,
            endpoint,
            policy=policy,
            timeout_seconds=timeout_seconds,
            disable_after_consecutive_failures=disable_after_consecutive_failures,
            transport=transport,
        )
        attempted += 1

    return attempted
