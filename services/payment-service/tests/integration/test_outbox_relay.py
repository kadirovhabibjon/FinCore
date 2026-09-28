import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fincore_common.events import EventEnvelope
from fincore_common.kafka import EventConsumer, EventProducer

from app.core.config import settings
from app.core.metrics import OUTBOX_BACKLOG
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.repositories.outbox_repository import OutboxRepository
from app.services.outbox import drain_outbox, relay_outbox_events

pytestmark = pytest.mark.usefixtures("migrated_database")

# `kafka_bootstrap_servers` (module-scoped) comes from
# tests/integration/conftest.py.


async def _insert_outbox_row(
    *, aggregate_id: str, event_type: str, payload: dict, aggregate_type: str = "Transfer"
) -> uuid.UUID:
    async with db_session.async_session_factory() as session:
        row = OutboxEvent(
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            event_type=event_type,
            payload=payload,
            correlation_id="corr-relay-test",
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def test_relay_routes_payment_events_to_the_payments_topic_not_transfers(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "transfers_topic", "test-relay-transfers-4")
    monkeypatch.setattr(settings, "payments_topic", "test-relay-payments-4")
    await _insert_outbox_row(
        aggregate_id="p-relay-1",
        event_type="payment.completed",
        payload={"payment_id": "p-relay-1"},
        aggregate_type="Payment",
    )

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            published_count = await relay_outbox_events(session, producer)
    finally:
        await producer.stop()

    assert published_count == 1

    received: list[EventEnvelope] = []

    async def collector(event: EventEnvelope) -> None:
        received.append(event)

    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["test-relay-payments-4"],
        group_id="test-relay-group-4",
    )
    await consumer.start()
    try:
        await consumer.run(collector, max_messages=1)
    finally:
        await consumer.stop()

    assert len(received) == 1
    assert received[0].data == {"payment_id": "p-relay-1"}

    # Nothing ever landed on the transfers topic.
    empty_consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["test-relay-transfers-4"],
        group_id="test-relay-group-4b",
    )
    await empty_consumer.start()
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(empty_consumer.run(collector, max_messages=1), timeout=5)
    finally:
        await empty_consumer.stop()


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


async def test_drain_publishes_a_backlog_larger_than_one_batch_in_a_single_call(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Relaying one batch per tick capped throughput at batch_size /
    interval; draining must keep going until the backlog is gone.
    """
    monkeypatch.setattr(settings, "transfers_topic", "test-relay-drain")
    monkeypatch.setattr(settings, "outbox_relay_batch_size", 4)
    for i in range(10):
        await _insert_outbox_row(
            aggregate_id=f"t-drain-{i}",
            event_type="transfer.completed",
            payload={"transfer_id": f"t-drain-{i}"},
        )

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        published = await drain_outbox(producer)
    finally:
        await producer.stop()

    assert published == 10
    async with db_session.async_session_factory() as session:
        assert await OutboxRepository(session).count_unpublished() == 0


async def test_drain_stops_on_unroutable_rows_instead_of_spinning(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A full batch of rows the relay can't route is fetched again every
    pass — draining must stop on what was *published*, not fetched."""
    monkeypatch.setattr(settings, "outbox_relay_batch_size", 3)
    for i in range(3):
        await _insert_outbox_row(
            aggregate_id=f"x-{i}",
            event_type="transfer.completed",
            payload={},
            aggregate_type="Unknown",
        )

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        published = await asyncio.wait_for(drain_outbox(producer), timeout=10)
    finally:
        await producer.stop()

    assert published == 0


async def test_drain_keeps_the_backlog_gauge_current(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "transfers_topic", "test-relay-gauge")
    monkeypatch.setattr(settings, "outbox_relay_batch_size", 2)
    for i in range(5):
        await _insert_outbox_row(
            aggregate_id=f"t-gauge-{i}",
            event_type="transfer.completed",
            payload={"transfer_id": f"t-gauge-{i}"},
        )
    OUTBOX_BACKLOG.set(999)

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        await drain_outbox(producer)
    finally:
        await producer.stop()

    assert OUTBOX_BACKLOG._value.get() == 0


class _FailingProducer:
    async def send_many(self, messages: list) -> None:
        raise RuntimeError("broker rejected the batch")


async def test_a_failed_batch_send_leaves_every_row_unpublished_for_the_next_pass() -> None:
    """Which messages of a failed batch landed is unknowable, so none may
    be marked published — the whole batch goes again (at-least-once;
    consumers deduplicate on event_id)."""
    for i in range(3):
        await _insert_outbox_row(
            aggregate_id=f"t-fail-{i}", event_type="transfer.completed", payload={}
        )

    with pytest.raises(RuntimeError):
        async with db_session.async_session_factory() as session:
            await relay_outbox_events(session, _FailingProducer())  # type: ignore[arg-type]

    async with db_session.async_session_factory() as session:
        assert await OutboxRepository(session).count_unpublished() == 3
