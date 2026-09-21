import logging
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from fincore_common import EventEnvelope
from sqlalchemy.exc import IntegrityError

from app.db import session as db_session
from app.domain.webhook_delivery import WebhookDelivery
from app.repositories.webhook_delivery_repository import WebhookDeliveryRepository
from app.repositories.webhook_endpoint_repository import WebhookEndpointRepository

logger = logging.getLogger(__name__)


class UnhandledEventTypeError(Exception):
    pass


def _build_outbound_payload(envelope: EventEnvelope) -> dict[str, Any]:
    """The body actually sent to a merchant's endpoint (spec Section
    17's example event) — a stable, minimal shape independent of
    whatever fields payment-service's own outbox payload happens to
    carry, so an unrelated internal field never leaks into a
    third-party HTTP call.
    """
    data = envelope.data
    return {
        "event_id": str(envelope.event_id),
        "event": envelope.event_type.value,
        "payment_id": data["payment_id"],
        "reference": data["reference"],
        "amount_minor": data["amount_minor"],
        "currency": data["currency"],
        "status": data["status"],
        "occurred_at": envelope.occurred_at.isoformat(),
    }


async def handle_payment_event(envelope: EventEnvelope) -> None:
    """The Kafka consumer's message handler (app/main.py). Fans one
    event out to a `WebhookDelivery` row per active endpoint registered
    for its merchant (spec Section 17) — idempotent per (endpoint,
    event_id) pair, so a redelivered Kafka message (at-least-once,
    spec Section 14.1) never creates a second delivery for the same
    endpoint.

    Deliberately does not perform any HTTP call itself: it only records
    that a delivery is owed, durably, before the Kafka offset commits.
    The actual attempt is made later by the delivery worker
    (app/services/delivery.py), independently of this consumer loop.
    """
    data = envelope.data
    try:
        merchant_id = UUID(data["merchant_id"])
    except KeyError as exc:
        raise UnhandledEventTypeError(f"event missing merchant_id: {envelope.event_type}") from exc

    payload = _build_outbound_payload(envelope)
    now = datetime.now(UTC)

    async with db_session.async_session_factory() as session:
        endpoint_repository = WebhookEndpointRepository(session)
        delivery_repository = WebhookDeliveryRepository(session)
        endpoints = await endpoint_repository.list_active_for_merchant(merchant_id)

        for endpoint in endpoints:
            if await delivery_repository.exists_for_endpoint_and_event(
                endpoint.id, envelope.event_id
            ):
                continue

            session.add(
                WebhookDelivery(
                    endpoint_id=endpoint.id,
                    event_id=envelope.event_id,
                    event_type=envelope.event_type.value,
                    payload=payload,
                    next_attempt_at=now,
                )
            )
            try:
                await session.commit()
            except IntegrityError:
                # Lost a race against another delivery of the same Kafka
                # message (e.g. a consumer restart between commit and
                # offset commit) — the UNIQUE(endpoint_id, event_id)
                # constraint is the real guard, the pre-check above is
                # only the fast path.
                await session.rollback()
                logger.info(
                    "delivery for endpoint %s event %s already recorded; skipping",
                    endpoint.id,
                    envelope.event_id,
                )
