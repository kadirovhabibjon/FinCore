import asyncio
import uuid
from unittest.mock import patch

import pytest
from fincore_common import EventEnvelope, EventType
from fincore_common.kafka import EventConsumer, EventProducer
from sqlalchemy import select

from app.core.metrics import DLT_MESSAGES_TOTAL
from app.db import session as db_session
from app.domain.audit_log import AuditLog
from app.domain.dead_letter import DeadLetter
from app.services.dispatch import process_retry_topic_message, process_with_retry_routing
from app.services.retry import RetryPolicy

pytestmark = pytest.mark.usefixtures("migrated_database")

_FAST_POLICY = RetryPolicy(max_attempts=3, base_delay_seconds=0.05, jitter_ratio=0.0)


def _completed_envelope(**overrides: object) -> EventEnvelope:
    data = {
        "transfer_id": str(uuid.uuid4()),
        "reference": "TRF-AUDIT-RETRY001",
        "initiator_user_id": str(uuid.uuid4()),
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


async def _audit_log_for(event_id: uuid.UUID) -> AuditLog | None:
    async with db_session.async_session_factory() as session:
        result = await session.execute(select(AuditLog).where(AuditLog.event_id == event_id))
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
    retry_topic = "test-audit-permanent-retry"
    dlt_topic = "test-audit-permanent-dlt"
    # Missing "status" -> handle_domain_event raises MalformedEventError,
    # classified as permanent (a producer bug, not a timeout).
    envelope = _completed_envelope()
    del envelope.data["status"]
    dlt_counter_before = DLT_MESSAGES_TOTAL._value.get()

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        await process_with_retry_routing(
            envelope,
            attempt=1,
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
    assert DLT_MESSAGES_TOTAL._value.get() == dlt_counter_before + 1

    await _assert_topic_is_empty(kafka_bootstrap_servers, retry_topic, "test-audit-permanent-group")


async def test_a_transient_error_succeeds_after_one_retry(kafka_bootstrap_servers: str) -> None:
    retry_topic = "test-audit-transient-success-retry"
    dlt_topic = "test-audit-transient-success-dlt"
    envelope = _completed_envelope()

    call_count = 0
    from app.services import consumer as consumer_module

    real_persist = consumer_module.persist_audit_log

    async def _flaky_persist(env: EventEnvelope) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("simulated transient database error")
        await real_persist(env)

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        with patch("app.services.dispatch.persist_audit_log", side_effect=_flaky_persist):
            await process_with_retry_routing(
                envelope,
                attempt=1,
                side_channel_producer=producer,
                retry_topic=retry_topic,
                dlt_topic=dlt_topic,
                policy=_FAST_POLICY,
            )

            assert await _audit_log_for(envelope.event_id) is None  # not yet — still failing

            retry_consumer = EventConsumer(
                bootstrap_servers=kafka_bootstrap_servers,
                topics=[retry_topic],
                group_id="test-audit-transient-success-group",
            )
            await retry_consumer.start()
            try:
                await retry_consumer.run(
                    lambda e: process_retry_topic_message(
                        e,
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

    assert call_count == 2
    audit_log = await _audit_log_for(envelope.event_id)
    assert audit_log is not None
    assert await _dead_letter_for(envelope.event_id) is None


async def test_a_transient_error_that_never_recovers_is_dead_lettered_after_max_attempts(
    kafka_bootstrap_servers: str,
) -> None:
    retry_topic = "test-audit-transient-exhausted-retry"
    dlt_topic = "test-audit-transient-exhausted-dlt"
    envelope = _completed_envelope()
    policy = RetryPolicy(max_attempts=2, base_delay_seconds=0.05, jitter_ratio=0.0)

    async def _always_fails(_: EventEnvelope) -> None:
        raise RuntimeError("simulated persistent database outage")

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        with patch("app.services.dispatch.persist_audit_log", side_effect=_always_fails):
            await process_with_retry_routing(
                envelope,
                attempt=1,
                side_channel_producer=producer,
                retry_topic=retry_topic,
                dlt_topic=dlt_topic,
                policy=policy,
            )

            retry_consumer = EventConsumer(
                bootstrap_servers=kafka_bootstrap_servers,
                topics=[retry_topic],
                group_id="test-audit-transient-exhausted-group",
            )
            await retry_consumer.start()
            try:
                await retry_consumer.run(
                    lambda e: process_retry_topic_message(
                        e,
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

    dead_letter = await _dead_letter_for(envelope.event_id)
    assert dead_letter is not None
    assert dead_letter.attempts == 2
    assert await _audit_log_for(envelope.event_id) is None
