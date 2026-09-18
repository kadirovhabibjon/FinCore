import uuid

import pytest
from fincore_common import EventEnvelope, EventType
from fincore_common.kafka import EventConsumer, EventProducer
from httpx import ASGITransport, AsyncClient

from app.core import kafka as kafka_module
from app.core.config import settings
from app.core.exceptions import AlreadyReplayedError
from app.db import session as db_session
from app.domain.dead_letter import DeadLetter
from app.main import app
from app.services.replay import replay_dead_letter

pytestmark = pytest.mark.usefixtures("migrated_database")


def _envelope() -> EventEnvelope:
    return EventEnvelope(
        event_type=EventType.TRANSFER_COMPLETED,
        producer="payment-service",
        data={
            "transfer_id": str(uuid.uuid4()),
            "reference": "TRF-REPLAY001",
            "initiator_user_id": str(uuid.uuid4()),
            "amount_minor": 500_00,
            "currency": "UZS",
            "status": "COMPLETED",
            "failure_reason": None,
            "completed_at": "2026-01-01T00:00:00Z",
        },
    )


async def _insert_dead_letter(envelope: EventEnvelope, *, topic: str) -> DeadLetter:
    async with db_session.async_session_factory() as session:
        row = DeadLetter(
            event_id=envelope.event_id,
            topic=topic,
            envelope=envelope.model_dump(mode="json"),
            last_error="simulated failure",
            attempts=1,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def test_replaying_republishes_the_original_event_and_marks_it_replayed(
    kafka_bootstrap_servers: str,
) -> None:
    topic = "test-replay-main"
    envelope = _envelope()
    dead_letter = await _insert_dead_letter(envelope, topic="test-replay-dlt")

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            row = await session.get(DeadLetter, dead_letter.id)
            assert row is not None
            await replay_dead_letter(session, row, producer, topic)
    finally:
        await producer.stop()

    async with db_session.async_session_factory() as session:
        row = await session.get(DeadLetter, dead_letter.id)
        assert row is not None
        assert row.replayed_at is not None

    received: list[EventEnvelope] = []

    async def collector(event: EventEnvelope) -> None:
        received.append(event)

    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers, topics=[topic], group_id="test-replay-group"
    )
    await consumer.start()
    try:
        await consumer.run(collector, max_messages=1)
    finally:
        await consumer.stop()

    assert len(received) == 1
    assert received[0].event_id == envelope.event_id


async def test_replaying_an_already_replayed_dead_letter_is_rejected(
    kafka_bootstrap_servers: str,
) -> None:
    envelope = _envelope()
    dead_letter = await _insert_dead_letter(envelope, topic="test-replay-dlt-2")

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            row = await session.get(DeadLetter, dead_letter.id)
            assert row is not None
            await replay_dead_letter(session, row, producer, "test-replay-main-2")

        async with db_session.async_session_factory() as session:
            row = await session.get(DeadLetter, dead_letter.id)
            assert row is not None
            with pytest.raises(AlreadyReplayedError):
                await replay_dead_letter(session, row, producer, "test-replay-main-2")
    finally:
        await producer.stop()


async def test_the_replay_endpoint_lists_and_replays_through_http(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_producer = EventProducer(kafka_bootstrap_servers)
    await real_producer.start()
    monkeypatch.setattr(kafka_module, "side_channel_producer", real_producer)
    try:
        envelope = _envelope()
        dead_letter = await _insert_dead_letter(envelope, topic="test-replay-dlt-3")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            headers = {"X-Internal-Token": settings.internal_service_token}

            listed = await client.get("/internal/v1/dead-letters", headers=headers)
            assert listed.status_code == 200
            assert any(item["id"] == str(dead_letter.id) for item in listed.json())

            replayed = await client.post(
                f"/internal/v1/dead-letters/{dead_letter.id}/replay", headers=headers
            )
            assert replayed.status_code == 204

            second_attempt = await client.post(
                f"/internal/v1/dead-letters/{dead_letter.id}/replay", headers=headers
            )
            assert second_attempt.status_code == 409

            missing = await client.post(
                f"/internal/v1/dead-letters/{uuid.uuid4()}/replay", headers=headers
            )
            assert missing.status_code == 404

            unauthorized = await client.get("/internal/v1/dead-letters")
            assert unauthorized.status_code in (401, 403, 422)
    finally:
        await real_producer.stop()
