import asyncio

import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from testcontainers.community.kafka import KafkaContainer

from fincore_common.events import EventEnvelope, EventType
from fincore_common.kafka import EventConsumer, EventProducer


@pytest.fixture(scope="module")
def bootstrap_servers() -> str:
    # Single-node KRaft mode — no separate Zookeeper container needed,
    # same setup used in docker-compose.yml for local dev.
    with KafkaContainer().with_kraft() as kafka:
        yield kafka.get_bootstrap_server()


async def _send(bootstrap_servers: str, topic: str, *, key: str, envelope: EventEnvelope) -> None:
    producer = EventProducer(bootstrap_servers)
    await producer.start()
    try:
        await producer.send(topic, key=key, envelope=envelope)
    finally:
        await producer.stop()


def _collector(sink: list[EventEnvelope]):
    async def handler(event: EventEnvelope) -> None:
        sink.append(event)

    return handler


async def test_a_produced_event_is_received_with_its_key_and_correlation_id(
    bootstrap_servers: str,
) -> None:
    topic = "test-transfers-1"
    await _send(
        bootstrap_servers,
        topic,
        key="t-1",
        envelope=EventEnvelope(
            event_type=EventType.TRANSFER_COMPLETED,
            producer="payment-service",
            correlation_id="corr-xyz",
            data={"transfer_id": "t-1"},
        ),
    )

    received: list[EventEnvelope] = []
    consumer = EventConsumer(
        bootstrap_servers=bootstrap_servers, topics=[topic], group_id="test-group-1"
    )
    await consumer.start()
    try:
        await consumer.run(_collector(received), max_messages=1)
    finally:
        await consumer.stop()

    assert len(received) == 1
    assert received[0].data == {"transfer_id": "t-1"}
    assert received[0].correlation_id == "corr-xyz"


async def test_a_failed_handler_leaves_the_message_uncommitted_for_redelivery(
    bootstrap_servers: str,
) -> None:
    """The core promise of EventConsumer: a handler that raises must not
    have its message silently marked done — that would turn a transient
    failure into a dropped event (spec Section 14.1's at-least-once
    delivery). A later consumer in the same group must still see it.
    """
    topic = "test-transfers-2"
    group_id = "test-group-2"
    await _send(
        bootstrap_servers,
        topic,
        key="k-1",
        envelope=EventEnvelope(
            event_type=EventType.TRANSFER_COMPLETED, producer="payment-service", data={"n": 1}
        ),
    )

    async def failing_handler(event: EventEnvelope) -> None:
        raise RuntimeError("simulated processing failure")

    failing_consumer = EventConsumer(
        bootstrap_servers=bootstrap_servers, topics=[topic], group_id=group_id
    )
    await failing_consumer.start()
    try:
        with pytest.raises(RuntimeError):
            await failing_consumer.run(failing_handler, max_messages=1)
    finally:
        await failing_consumer.stop()

    received: list[EventEnvelope] = []
    retry_consumer = EventConsumer(
        bootstrap_servers=bootstrap_servers, topics=[topic], group_id=group_id
    )
    await retry_consumer.start()
    try:
        await retry_consumer.run(_collector(received), max_messages=1)
    finally:
        await retry_consumer.stop()

    assert len(received) == 1
    assert received[0].data == {"n": 1}

    # And once a handler *does* succeed, the offset is genuinely
    # committed: a third consumer in the same group sees nothing new.
    third_received: list[EventEnvelope] = []
    third_consumer = EventConsumer(
        bootstrap_servers=bootstrap_servers, topics=[topic], group_id=group_id
    )
    await third_consumer.start()
    try:
        with pytest.raises(TimeoutError):
            await asyncio.wait_for(
                third_consumer.run(_collector(third_received), max_messages=1), timeout=5
            )
    finally:
        await third_consumer.stop()

    assert third_received == []


async def test_trace_context_propagates_from_producer_to_consumer(bootstrap_servers: str) -> None:
    """The whole point of injecting/extracting trace context into Kafka
    headers (spec Section 24's "correlation ID propagated through ...
    Kafka events," done here with real span context, not just the
    string): a trace started before publishing must continue as the
    parent of the consumer's own processing span, not start a second,
    disconnected trace.
    """
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    tracer = trace.get_tracer("test")

    topic = "test-tracing-1"
    envelope = EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED, producer="test", data={"n": 1}
    )

    producer = EventProducer(bootstrap_servers)
    await producer.start()
    try:
        with tracer.start_as_current_span("caller span") as caller_span:
            expected_trace_id = caller_span.get_span_context().trace_id
            await producer.send(topic, key="k-1", envelope=envelope)
    finally:
        await producer.stop()

    consumer = EventConsumer(
        bootstrap_servers=bootstrap_servers, topics=[topic], group_id="test-tracing-group"
    )
    await consumer.start()
    try:
        await consumer.run(_collector([]), max_messages=1)
    finally:
        await consumer.stop()

    span_names = {span.name: span for span in exporter.get_finished_spans()}
    assert "caller span" in span_names
    assert f"{topic} publish" in span_names
    assert f"{topic} process" in span_names
    # All three spans belong to the one trace the caller started —
    # proof the context actually crossed the Kafka boundary rather than
    # the consumer starting a fresh, unrelated trace.
    for span in span_names.values():
        assert span.get_span_context().trace_id == expected_trace_id
