import asyncio
import uuid

import pytest
from fincore_common import EventEnvelope, EventType
from fincore_common.kafka import EventConsumer, EventProducer
from sqlalchemy import select

from app.db import session as db_session
from app.domain.dead_letter import DeadLetter
from app.domain.notification import Notification
from app.services.dispatch import process_retry_topic_message, process_with_retry_routing
from app.services.providers import ProviderUnavailableError
from app.services.retry import RetryPolicy

pytestmark = pytest.mark.usefixtures("migrated_database")

_FAST_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=0.05, jitter_ratio=0.0)


class _FlakyProvider:
    def __init__(self, channel: str, fail_times: int) -> None:
        self.channel = channel
        self._remaining_failures = fail_times
        self.calls = 0

    async def send(self, *, recipient_user_id: uuid.UUID, subject: str, body: str) -> None:
        self.calls += 1
        if self._remaining_failures > 0:
            self._remaining_failures -= 1
            raise ProviderUnavailableError("simulated provider outage")


def _completed_envelope(user_id: uuid.UUID, **overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-RETRY001",
        "initiator_user_id": str(user_id),
        "amount_minor": 100_00,
        "currency": "UZS",
        "status": "COMPLETED",
        "failure_reason": None,
        "completed_at": "2026-01-01T00:00:00Z",
    }
    data.update(overrides)
    return EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED, producer="payment-service", data=data
    )


async def _dead_letter_for(event_id: uuid.UUID) -> DeadLetter | None:
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(DeadLetter).where(DeadLetter.event_id == event_id))
        return result.scalar_one_or_none()


async def _notification_for(event_id: uuid.UUID) -> Notification | None:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(Notification).where(Notification.event_id == event_id)
        )
        return result.scalar_one_or_none()


async def _assert_topic_is_empty(bootstrap_servers: str, topic: str, group_id: str) -> None:
    consumer = EventConsumer(bootstrap_servers=bootstrap_servers, topics=[topic], group_id=group_id)
    await consumer.start()
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(consumer.run(_noop, max_messages=1), timeout=3)
    finally:
        await consumer.stop()


async def _noop(_: EventEnvelope) -> None:
    return None


async def test_a_permanent_error_goes_straight_to_the_dlt_without_retrying(
    kafka_bootstrap_servers: str,
) -> None:
    retry_topic = "test-permanent-retry"
    dlt_topic = "test-permanent-dlt"
    # Missing "initiator_user_id" -> compose_transfer_message raises
    # KeyError, classified as permanent (a producer bug, not a timeout).
    envelope = _completed_envelope(uuid.uuid4())
    del envelope.data["initiator_user_id"]

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        await process_with_retry_routing(
            envelope,
            attempt=1,
            providers=[],
            side_channel_producer=producer,
            retry_topic=retry_topic,
            dlt_topic=dlt_topic,
            policy=_FAST_POLICY,
        )
    finally:
        await producer.stop()

    dead_letter = await _dead_letter_for(envelope.event_id)
    assert dead_letter is not None
    assert dead_letter.attempts == 1
    assert dead_letter.topic == dlt_topic

    await _assert_topic_is_empty(kafka_bootstrap_servers, retry_topic, "test-permanent-group")


async def test_a_transient_error_succeeds_after_one_retry(kafka_bootstrap_servers: str) -> None:
    retry_topic = "test-transient-success-retry"
    dlt_topic = "test-transient-success-dlt"
    user_id = uuid.uuid4()
    envelope = _completed_envelope(user_id)
    provider = _FlakyProvider("EMAIL", fail_times=1)

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        await process_with_retry_routing(
            envelope,
            attempt=1,
            providers=[provider],
            side_channel_producer=producer,
            retry_topic=retry_topic,
            dlt_topic=dlt_topic,
            policy=_FAST_POLICY,
        )

        assert await _notification_for(envelope.event_id) is None  # not yet — still failing

        retry_consumer = EventConsumer(
            bootstrap_servers=kafka_bootstrap_servers,
            topics=[retry_topic],
            group_id="test-transient-success-group",
        )
        await retry_consumer.start()
        try:
            await retry_consumer.run(
                lambda e: process_retry_topic_message(
                    e,
                    providers=[provider],
                    side_channel_producer=producer,
                    retry_topic=retry_topic,
                    dlt_topic=dlt_topic,
                    policy=_FAST_POLICY,
                ),
                max_messages=1,
            )
        finally:
            await retry_consumer.stop()
    finally:
        await producer.stop()

    assert provider.calls == 2
    notification = await _notification_for(envelope.event_id)
    assert notification is not None
    assert notification.recipient_user_id == user_id
    assert await _dead_letter_for(envelope.event_id) is None


async def test_a_transient_error_that_never_recovers_is_dead_lettered_after_max_attempts(
    kafka_bootstrap_servers: str,
) -> None:
    retry_topic = "test-transient-exhausted-retry"
    dlt_topic = "test-transient-exhausted-dlt"
    envelope = _completed_envelope(uuid.uuid4())
    provider = _FlakyProvider("EMAIL", fail_times=99)
    policy = RetryPolicy(max_attempts=2, base_delay_seconds=0.05, jitter_ratio=0.0)

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        await process_with_retry_routing(
            envelope,
            attempt=1,
            providers=[provider],
            side_channel_producer=producer,
            retry_topic=retry_topic,
            dlt_topic=dlt_topic,
            policy=policy,
        )

        retry_consumer = EventConsumer(
            bootstrap_servers=kafka_bootstrap_servers,
            topics=[retry_topic],
            group_id="test-transient-exhausted-group",
        )
        await retry_consumer.start()
        try:
            await retry_consumer.run(
                lambda e: process_retry_topic_message(
                    e,
                    providers=[provider],
                    side_channel_producer=producer,
                    retry_topic=retry_topic,
                    dlt_topic=dlt_topic,
                    policy=policy,
                ),
                max_messages=1,
            )
        finally:
            await retry_consumer.stop()
    finally:
        await producer.stop()

    assert provider.calls == 2
    dead_letter = await _dead_letter_for(envelope.event_id)
    assert dead_letter is not None
    assert dead_letter.attempts == 2
    assert await _notification_for(envelope.event_id) is None
