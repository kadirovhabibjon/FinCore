from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer

from .correlation import new_correlation_id, reset_correlation_id, set_correlation_id
from .events import EventEnvelope

logger = logging.getLogger(__name__)

EventHandler = Callable[[EventEnvelope], Awaitable[None]]


class EventProducer:
    """Publishes `EventEnvelope`s to Kafka (spec Section 14.2) — the last
    step of a service's outbox relay (Section 14.1), never called
    directly from a request handler.
    """

    def __init__(self, bootstrap_servers: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._producer: AIOKafkaProducer | None = None

    async def start(self) -> None:
        # Built here, not in __init__: AIOKafkaProducer binds to the
        # running asyncio event loop at construction time, so building
        # it eagerly would break every service's existing pattern of
        # constructing its singleton clients at *module import* time
        # (e.g. ledger_client, jwt_verifier) — there is no running loop
        # yet at that point.
        self._producer = AIOKafkaProducer(bootstrap_servers=self._bootstrap_servers)
        await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def send(self, topic: str, *, key: str, envelope: EventEnvelope) -> None:
        """`key` is the aggregate id (spec's `OutboxEvent.aggregate_id`)
        — Kafka guarantees per-key ordering by always routing the same
        key to the same partition, so every event for one aggregate
        (e.g. one Transfer) is delivered to a given consumer in order.
        """
        if self._producer is None:
            raise RuntimeError("EventProducer.start() must be called before send()")
        await self._producer.send_and_wait(
            topic,
            key=key.encode("utf-8"),
            value=envelope.model_dump_json().encode("utf-8"),
        )


class EventConsumer:
    """Consumes `EventEnvelope`s from Kafka and hands each to `handler`,
    committing its offset only after the handler returns without
    raising.

    That ordering is deliberate: a crash between "handler ran" and
    "offset committed" redelivers the same message on restart —
    at-least-once delivery (spec Section 14.1) — so `handler` must be
    idempotent (Section 14.3's "consumer idempotency"), not this class's
    job to guarantee.
    """

    def __init__(self, *, bootstrap_servers: str, topics: list[str], group_id: str) -> None:
        self._bootstrap_servers = bootstrap_servers
        self._topics = topics
        self._group_id = group_id
        self._consumer: AIOKafkaConsumer | None = None

    async def start(self) -> None:
        # Same reasoning as EventProducer.start(): built here, not in
        # __init__, since it needs a running event loop.
        self._consumer = AIOKafkaConsumer(
            *self._topics,
            bootstrap_servers=self._bootstrap_servers,
            group_id=self._group_id,
            enable_auto_commit=False,
            auto_offset_reset="earliest",
        )
        await self._consumer.start()

    async def stop(self) -> None:
        if self._consumer is not None:
            await self._consumer.stop()
            self._consumer = None

    async def run(self, handler: EventHandler, *, max_messages: int | None = None) -> None:
        """Consumes forever by default. `max_messages` returns after that
        many messages have each been fully handled and committed — used
        by tests to bound an otherwise-infinite loop deterministically,
        without racing an external cancellation against an in-flight
        commit.
        """
        if self._consumer is None:
            raise RuntimeError("EventConsumer.start() must be called before run()")
        processed = 0
        async for message in self._consumer:
            envelope = EventEnvelope.model_validate_json(message.value)
            token = set_correlation_id(envelope.correlation_id or new_correlation_id())
            try:
                await handler(envelope)
                await self._consumer.commit()
            finally:
                reset_correlation_id(token)
            processed += 1
            if max_messages is not None and processed >= max_messages:
                return
