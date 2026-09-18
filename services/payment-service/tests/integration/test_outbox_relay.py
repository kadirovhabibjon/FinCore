import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fincore_common.events import EventEnvelope
from fincore_common.kafka import EventConsumer, EventProducer

from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.services.outbox import relay_outbox_events

pytestmark = pytest.mark.usefixtures("migrated_database")

# `kafka_bootstrap_servers` (module-scoped) comes from
# tests/integration/conftest.py.


async def _insert_outbox_row(*, aggregate_id: str, event_type: str, payload: dict) -> uuid.UUID:
    async with db_session.async_session_factory() as session:
        row = OutboxEvent(
            aggregate_type="Transfer",
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            correlation_id="corr-relay-test",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def test_relay_publishes_unpublished_rows_and_marks_them_published(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "transfers_topic", "test-relay-transfers-1")
    row_id = await _insert_outbox_row(
        aggregate_id="t-relay-1",
        event_type="transfer.completed",
        payload={"transfer_id": "t-relay-1", "amount_minor": 100},
    )

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            published_count = await relay_outbox_events(session, producer)
    finally:
        await producer.stop()

    assert published_count == 1

    async with db_session.async_session_factory() as session:
        row = await session.get(OutboxEvent, row_id)
        assert row is not None
        assert row.published_at is not None

    received: list[EventEnvelope] = []

    async def collector(event: EventEnvelope) -> None:
        received.append(event)

    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["test-relay-transfers-1"],
        group_id="test-relay-group-1",
    )
    await consumer.start()
    try:
        await consumer.run(collector, max_messages=1)
    finally:
        await consumer.stop()

    assert len(received) == 1
    assert received[0].event_id == row_id
    assert received[0].correlation_id == "corr-relay-test"
    assert received[0].data == {"transfer_id": "t-relay-1", "amount_minor": 100}


async def test_relay_does_not_republish_already_published_rows(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "transfers_topic", "test-relay-transfers-2")
    await _insert_outbox_row(
        aggregate_id="t-relay-2", event_type="transfer.completed", payload={"n": 1}
    )

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            first_pass = await relay_outbox_events(session, producer)
        async with db_session.async_session_factory() as session:
            second_pass = await relay_outbox_events(session, producer)
    finally:
        await producer.stop()

    assert first_pass == 1
    assert second_pass == 0


async def test_relay_processes_oldest_unpublished_rows_first(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "transfers_topic", "test-relay-transfers-3")

    async with db_session.async_session_factory() as session:
        older = OutboxEvent(
            aggregate_type="Transfer",
            aggregate_id="t-relay-older",
            event_type="transfer.completed",
            payload={"order": "older"},
        )
        newer = OutboxEvent(
            aggregate_type="Transfer",
            aggregate_id="t-relay-newer",
            event_type="transfer.completed",
            payload={"order": "newer"},
        )
        session.add_all([older, newer])
        await session.flush()
        # created_at both default to now() at flush time; force a real
        # ordering so this test doesn't depend on same-millisecond luck.
        older.created_at = datetime.now(UTC) - timedelta(seconds=10)
        await session.commit()

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            await relay_outbox_events(session, producer)
    finally:
        await producer.stop()

    received: list[EventEnvelope] = []

    async def collector(event: EventEnvelope) -> None:
        received.append(event)

    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["test-relay-transfers-3"],
        group_id="test-relay-group-3",
    )
    await consumer.start()
    try:
        await consumer.run(collector, max_messages=2)
    finally:
        await consumer.stop()

    assert [event.data["order"] for event in received] == ["older", "newer"]
