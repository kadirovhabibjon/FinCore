import uuid
from datetime import UTC, datetime

import pytest
from fincore_common import EventEnvelope, EventType

from app.db import session as db_session
from app.domain.webhook_endpoint import WebhookEndpoint, WebhookEndpointStatus
from app.repositories.webhook_delivery_repository import WebhookDeliveryRepository
from app.services.consumer import UnhandledEventTypeError, handle_payment_event

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _create_endpoint(
    *, merchant_id: uuid.UUID, status: WebhookEndpointStatus = WebhookEndpointStatus.ACTIVE
) -> WebhookEndpoint:
    async with db_session.async_session_factory() as session:
        endpoint = WebhookEndpoint(
            merchant_id=merchant_id,
            owner_user_id=uuid.uuid4(),
            url="https://merchant.example.com/hook",
            secret="test-secret",
            status=status,
        )
        session.add(endpoint)
        await session.commit()
        await session.refresh(endpoint)
        return endpoint


def _payment_completed_envelope(
    *, merchant_id: uuid.UUID, event_id: uuid.UUID | None = None
) -> EventEnvelope:
    return EventEnvelope(
        event_id=event_id or uuid.uuid4(),
        event_type=EventType.PAYMENT_COMPLETED,
        producer="payment-service",
        correlation_id="corr-1",
        data={
            "payment_id": str(uuid.uuid4()),
            "reference": "PAY-1",
            "initiator_user_id": str(uuid.uuid4()),
            "merchant_id": str(merchant_id),
            "amount_minor": 5000,
            "currency": "UZS",
            "status": "SUCCESS",
            "failure_reason": None,
            "completed_at": datetime.now(UTC).isoformat(),
        },
    )


async def test_creates_a_delivery_for_each_active_endpoint_of_the_merchant() -> None:
    merchant_id = uuid.uuid4()
    endpoint_a = await _create_endpoint(merchant_id=merchant_id)
    endpoint_b = await _create_endpoint(merchant_id=merchant_id)
    # A different merchant's endpoint must never see this event.
    await _create_endpoint(merchant_id=uuid.uuid4())

    envelope = _payment_completed_envelope(merchant_id=merchant_id)
    await handle_payment_event(envelope)

    async with db_session.async_session_factory() as session:
        repository = WebhookDeliveryRepository(session)
        assert await repository.exists_for_endpoint_and_event(endpoint_a.id, envelope.event_id)
        assert await repository.exists_for_endpoint_and_event(endpoint_b.id, envelope.event_id)


async def test_skips_disabled_endpoints() -> None:
    merchant_id = uuid.uuid4()
    disabled = await _create_endpoint(
        merchant_id=merchant_id, status=WebhookEndpointStatus.DISABLED
    )

    envelope = _payment_completed_envelope(merchant_id=merchant_id)
    await handle_payment_event(envelope)

    async with db_session.async_session_factory() as session:
        repository = WebhookDeliveryRepository(session)
        assert not await repository.exists_for_endpoint_and_event(disabled.id, envelope.event_id)


async def test_redelivery_of_the_same_event_is_idempotent() -> None:
    merchant_id = uuid.uuid4()
    endpoint = await _create_endpoint(merchant_id=merchant_id)
    envelope = _payment_completed_envelope(merchant_id=merchant_id)

    await handle_payment_event(envelope)
    await handle_payment_event(envelope)  # simulates Kafka's at-least-once redelivery

    async with db_session.async_session_factory() as session:
        deliveries = await WebhookDeliveryRepository(session).list_for_endpoint(
            endpoint.id, limit=10, offset=0
        )
    assert len(deliveries) == 1


async def test_event_missing_merchant_id_raises_unhandled_event_type_error() -> None:
    envelope = EventEnvelope(
        event_type=EventType.PAYMENT_COMPLETED,
        producer="payment-service",
        data={"payment_id": str(uuid.uuid4())},
    )
    with pytest.raises(UnhandledEventTypeError):
        await handle_payment_event(envelope)
