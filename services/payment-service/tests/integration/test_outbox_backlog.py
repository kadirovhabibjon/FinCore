import uuid
from datetime import UTC, datetime

import pytest

from app.db import session as db_session
from app.domain.outbox import OutboxEvent
from app.repositories.outbox_repository import OutboxRepository

pytestmark = pytest.mark.usefixtures("migrated_database")


def _event(*, published: bool) -> OutboxEvent:
    return OutboxEvent(
        aggregate_type="Transfer",
        aggregate_id=str(uuid.uuid4()),
        event_type="transfer.completed",
        payload={},
        published_at=datetime.now(UTC) if published else None,
    )


async def test_count_unpublished_ignores_already_published_rows() -> None:
    async with db_session.async_session_factory() as session:
        session.add(_event(published=False))
        session.add(_event(published=False))
        session.add(_event(published=True))
        await session.commit()

        count = await OutboxRepository(session).count_unpublished()

    assert count == 2


async def test_count_unpublished_is_not_limited_by_a_batch_size() -> None:
    """The whole reason this exists instead of `len(list_unpublished(...))`
    — a backlog bigger than one relay pass's batch must still report its
    true size.
    """
    async with db_session.async_session_factory() as session:
        for _ in range(5):
            session.add(_event(published=False))
        await session.commit()

        repository = OutboxRepository(session)
        batch = await repository.list_unpublished(limit=2)
        count = await repository.count_unpublished()

    assert len(batch) == 2
    assert count == 5
