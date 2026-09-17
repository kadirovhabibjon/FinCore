import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.core.exceptions import IdempotencyKeyConflictError, IdempotencyKeyInProgressError
from app.db import session as db_session
from app.domain.idempotency import IdempotencyKey, IdempotencyKeyStatus
from app.services.idempotency import (
    IdempotentReplayResponse,
    begin_idempotent_request,
    complete_idempotent_request,
)

pytestmark = pytest.mark.usefixtures("migrated_database")


async def test_begin_idempotent_request_creates_an_in_progress_row() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        record = await begin_idempotent_request(
            session, user_id=user_id, key="key-1", fingerprint="fp-1"
        )

    assert record.status == IdempotencyKeyStatus.IN_PROGRESS
    assert record.user_id == user_id


async def test_reusing_a_key_while_in_progress_is_rejected() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        await begin_idempotent_request(session, user_id=user_id, key="key-2", fingerprint="fp-2")

    async with db_session.async_session_factory() as session:
        with pytest.raises(IdempotencyKeyInProgressError):
            await begin_idempotent_request(
                session, user_id=user_id, key="key-2", fingerprint="fp-2"
            )


async def test_reusing_a_key_with_a_different_body_is_rejected() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        await begin_idempotent_request(session, user_id=user_id, key="key-3", fingerprint="fp-a")

    async with db_session.async_session_factory() as session:
        with pytest.raises(IdempotencyKeyConflictError):
            await begin_idempotent_request(
                session, user_id=user_id, key="key-3", fingerprint="fp-b"
            )


async def test_completed_request_is_replayed_without_rerunning_business_logic() -> None:
    user_id = uuid.uuid4()
    resource_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        record = await begin_idempotent_request(
            session, user_id=user_id, key="key-4", fingerprint="fp-4"
        )
        await complete_idempotent_request(
            session,
            record,
            status_code=201,
            body={"id": str(resource_id), "status": "COMPLETED"},
            resource_id=resource_id,
        )

    async with db_session.async_session_factory() as session:
        with pytest.raises(IdempotentReplayResponse) as excinfo:
            await begin_idempotent_request(
                session, user_id=user_id, key="key-4", fingerprint="fp-4"
            )

    assert excinfo.value.status_code == 201
    assert excinfo.value.body == {"id": str(resource_id), "status": "COMPLETED"}


async def test_different_users_can_reuse_the_same_key_value() -> None:
    # UNIQUE is (user_id, key) — the key string itself is only scoped
    # per user (spec Section 9.1).
    async with db_session.async_session_factory() as session:
        first = await begin_idempotent_request(
            session, user_id=uuid.uuid4(), key="shared-key", fingerprint="fp"
        )
    async with db_session.async_session_factory() as session:
        second = await begin_idempotent_request(
            session, user_id=uuid.uuid4(), key="shared-key", fingerprint="fp"
        )

    assert first.id != second.id


async def test_an_expired_key_is_reset_for_reuse_rather_than_blocking() -> None:
    user_id = uuid.uuid4()

    async with db_session.async_session_factory() as session:
        record = await begin_idempotent_request(
            session, user_id=user_id, key="key-expiring", fingerprint="fp-old"
        )

    async with db_session.async_session_factory() as session:
        stored = await session.get(IdempotencyKey, record.id)
        assert stored is not None
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with db_session.async_session_factory() as session:
        reused = await begin_idempotent_request(
            session, user_id=user_id, key="key-expiring", fingerprint="fp-new"
        )

    assert reused.id == record.id  # same row, reset in place
    assert reused.status == IdempotencyKeyStatus.IN_PROGRESS
    assert reused.request_fingerprint == "fp-new"


async def test_concurrent_requests_with_the_same_new_key_let_only_one_proceed() -> None:
    """The pre-check alone can't prevent this: two requests can both see
    no existing row before either commits. The UNIQUE(user_id, key)
    constraint is what actually decides — this proves it, rather than
    just asserting the code "should" behave this way.
    """
    user_id = uuid.uuid4()

    async def attempt() -> str:
        async with db_session.async_session_factory() as session:
            try:
                await begin_idempotent_request(
                    session, user_id=user_id, key="race-key", fingerprint="race-fp"
                )
                return "ok"
            except IdempotencyKeyInProgressError:
                return "in_progress"

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == ["in_progress", "ok"]
