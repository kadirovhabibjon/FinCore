import uuid

import pytest
from fincore_common.events import EventEnvelope, EventType
from fincore_common.kafka import EventConsumer, EventProducer
from sqlalchemy import select

from app.db import session as db_session
from app.domain.notification import Notification
from app.services.consumer import handle_transfer_event
from app.services.providers import default_providers

pytestmark = pytest.mark.usefixtures("migrated_database")


async def test_a_produced_transfer_completed_event_results_in_one_recorded_notification(
    kafka_bootstrap_servers: str,
) -> None:
    """The full pipeline this service exists for: something publishes to
    the "transfers" topic (payment-service's outbox relay, in
    production), and this service's own consumer loop
    (fincore_common.kafka.EventConsumer + app.services.consumer) turns
    that into a dispatched, recorded notification — exercised here
    against a real Kafka broker end to end, not a mocked one.
    """
    topic = "test-e2e-transfers"
    user_id = uuid.uuid4()
    envelope = EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED,
        producer="payment-service",
        data={
            "transfer_id": str(uuid.uuid4()),
            "reference": "TRF-E2E001",
            "initiator_user_id": str(user_id),
            "amount_minor": 750_00,
            "currency": "UZS",
            "status": "COMPLETED",
            "failure_reason": None,
            "completed_at": "2026-01-01T00:00:00Z",
        },
    )

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        await producer.send(topic, key=envelope.data["transfer_id"], envelope=envelope)
    finally:
        await producer.stop()

    providers = default_providers()
    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers, topics=[topic], group_id="test-e2e-group"
    )
    await consumer.start()
    try:
        await consumer.run(
            lambda event: handle_transfer_event(event, providers), max_messages=1
        )
    finally:
        await consumer.stop()

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(Notification).where(Notification.event_id == envelope.event_id)
        )
        row = result.scalar_one()

    assert row.recipient_user_id == user_id
    assert row.notification_type == "transfer.completed"
    assert "TRF-E2E001" in row.body
