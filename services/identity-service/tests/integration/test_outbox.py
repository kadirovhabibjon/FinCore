import uuid

import pytest
from fincore_common import EventType
from fincore_common.events import EventEnvelope
from fincore_common.kafka import EventConsumer, EventProducer
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app import cli
from app.core.config import settings
from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.domain.role import RoleName, UserRole
from app.domain.user import UserStatus
from app.main import app
from app.repositories.user_repository import UserRepository
from app.services.outbox import relay_outbox_events, user_outbox_event
from app.services.user_admin import change_user_status

pytestmark = pytest.mark.usefixtures("migrated_database")

_PASSWORD = "correct-horse-battery"


async def _register(email: str) -> uuid.UUID:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": email,
                "phone": f"+99890{uuid.uuid4().int % 10**7:07d}",
                "password": _PASSWORD,
                "first_name": "Test",
                "last_name": "User",
            },
        )
    assert response.status_code == 201
    return uuid.UUID(response.json()["id"])


async def _events(user_id: uuid.UUID) -> list[OutboxEvent]:
    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.aggregate_id == str(user_id))
            .order_by(OutboxEvent.created_at)
        )
        return list(result.scalars().all())


async def test_registration_records_user_registered() -> None:
    user_id = await _register("new@example.com")

    [event] = await _events(user_id)

    assert event.aggregate_type == "User"
    assert event.event_type == "user.registered"
    assert event.payload == {
        "user_id": str(user_id),
        "actor_user_id": str(user_id),
        "status": "ACTIVE",
    }
    assert event.published_at is None


async def test_status_changes_record_who_changed_what() -> None:
    admin_id = await _register("admin@example.com")
    user_id = await _register("target@example.com")

    async with db_session.async_session_factory() as session:
        await change_user_status(
            session, actor_id=admin_id, user_id=user_id, new_status=UserStatus.BLOCKED
        )
        # Setting the status it already has is a no-op: no event.
        await change_user_status(
            session, actor_id=admin_id, user_id=user_id, new_status=UserStatus.BLOCKED
        )
        await change_user_status(
            session, actor_id=admin_id, user_id=user_id, new_status=UserStatus.ACTIVE
        )

    events = await _events(user_id)
    assert [e.event_type for e in events] == [
        "user.registered",
        "user.blocked",
        "user.reactivated",
    ]
    assert events[1].payload == {
        "user_id": str(user_id),
        "actor_user_id": str(admin_id),
        "status": "BLOCKED",
        "previous_status": "ACTIVE",
    }
    assert events[2].payload["previous_status"] == "BLOCKED"


async def test_a_failed_status_change_records_nothing() -> None:
    admin_id = await _register("self@example.com")

    async with db_session.async_session_factory() as session:
        with pytest.raises(Exception, match=str(admin_id)):
            await change_user_status(
                session, actor_id=admin_id, user_id=admin_id, new_status=UserStatus.BLOCKED
            )

    assert [e.event_type for e in await _events(admin_id)] == ["user.registered"]


async def test_role_changes_from_the_cli_are_recorded_once() -> None:
    user_id = await _register("staff@example.com")

    await cli._change_role("staff@example.com", RoleName.SUPPORT, grant=True)
    await cli._change_role("staff@example.com", RoleName.SUPPORT, grant=True)  # no-op
    await cli._change_role("staff@example.com", RoleName.SUPPORT, grant=False)

    events = await _events(user_id)
    assert [e.event_type for e in events] == [
        "user.registered",
        "user.role_granted",
        "user.role_revoked",
    ]
    assert events[1].payload == {
        "user_id": str(user_id),
        "actor_user_id": None,
        "status": "ACTIVE",
        "role": "SUPPORT",
    }


async def test_the_event_and_the_change_commit_together() -> None:
    """A rolled-back role change leaves neither the role nor its event."""
    user_id = await _register("atomic@example.com")

    async with db_session.async_session_factory() as session:
        session.add(UserRole(user_id=user_id, role_name=RoleName.ADMIN.value))

        user = await UserRepository(session).get_by_id(user_id)
        assert user is not None
        session.add(
            user_outbox_event(user, EventType.USER_ROLE_GRANTED, actor_user_id=None, role="ADMIN")
        )
        await session.rollback()

    assert [e.event_type for e in await _events(user_id)] == ["user.registered"]


async def test_the_relay_publishes_to_the_users_topic_and_marks_rows(
    kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "users_topic", "test-identity-users")
    user_id = await _register("relay@example.com")

    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    try:
        async with db_session.async_session_factory() as session:
            assert await relay_outbox_events(session, producer) == 1
        async with db_session.async_session_factory() as session:
            assert await relay_outbox_events(session, producer) == 0  # already published
    finally:
        await producer.stop()

    received: list[EventEnvelope] = []

    async def collect(event: EventEnvelope) -> None:
        received.append(event)

    consumer = EventConsumer(
        bootstrap_servers=kafka_bootstrap_servers,
        topics=["test-identity-users"],
        group_id="test-identity-relay",
    )
    await consumer.start()
    try:
        await consumer.run(collect, max_messages=1)
    finally:
        await consumer.stop()

    [row] = await _events(user_id)
    assert row.published_at is not None
    assert received[0].event_id == row.id
    assert received[0].producer == "identity-service"
    assert received[0].data["user_id"] == str(user_id)
