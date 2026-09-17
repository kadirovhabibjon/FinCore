import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.core.exceptions import InvalidTokenError
from app.core.security import hash_refresh_token
from app.db import session as db_session
from app.domain.session import RefreshToken, Session
from app.domain.user import User
from app.services.registration import RegistrationData, register_user
from app.services.sessions import (
    revoke_session_by_refresh_token,
    rotate_refresh_token,
    start_session,
)

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _new_user() -> User:
    async with db_session.async_session_factory() as session:
        return await register_user(
            session,
            RegistrationData(
                email="turing@example.com",
                phone="+998988888888",
                password="enigma-bombe-1943",
                first_name="Alan",
                last_name="Turing",
            ),
        )


async def test_start_session_issues_a_usable_refresh_token() -> None:
    user = await _new_user()

    async with db_session.async_session_factory() as session:
        issued = await start_session(session, user.id)

    assert issued.user_id == user.id
    assert issued.expires_at > datetime.now(UTC)


async def test_rotate_refresh_token_issues_a_new_token_and_invalidates_the_old_one() -> None:
    user = await _new_user()
    async with db_session.async_session_factory() as session:
        first = await start_session(session, user.id)

    async with db_session.async_session_factory() as session:
        second = await rotate_refresh_token(session, first.token)

    assert second.token != first.token
    assert second.session_id == first.session_id

    # The old token is now spent — using it again must fail, not silently
    # issue a third token.
    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(session, first.token)


async def test_reusing_an_already_rotated_token_revokes_the_whole_session() -> None:
    user = await _new_user()
    async with db_session.async_session_factory() as session:
        first = await start_session(session, user.id)

    async with db_session.async_session_factory() as session:
        second = await rotate_refresh_token(session, first.token)

    # Replay the spent token — should fail *and* poison the session, so
    # even the legitimately-rotated `second` token stops working.
    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(session, first.token)

    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(session, second.token)


async def test_concurrent_redemption_of_the_same_token_lets_only_one_succeed() -> None:
    """The scenario the atomic UPDATE...WHERE guard exists for: two
    requests racing to redeem the same still-valid refresh token. Without
    the atomic claim, both could pass a naive `if used_at is None` check
    before either commits, minting two children from one token silently.
    """
    user = await _new_user()
    async with db_session.async_session_factory() as session:
        first = await start_session(session, user.id)

    async def attempt() -> str:
        async with db_session.async_session_factory() as session:
            try:
                await rotate_refresh_token(session, first.token)
                return "ok"
            except InvalidTokenError:
                return "rejected"

    results = await asyncio.gather(attempt(), attempt())

    assert sorted(results) == ["ok", "rejected"]


async def test_rotate_refresh_token_rejects_an_expired_token() -> None:
    user = await _new_user()
    async with db_session.async_session_factory() as session:
        issued = await start_session(session, user.id)

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(RefreshToken).where(
                RefreshToken.token_hash == hash_refresh_token(issued.token)
            )
        )
        stored = result.scalar_one()
        stored.expires_at = datetime.now(UTC) - timedelta(seconds=1)
        await session.commit()

    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(session, issued.token)


async def test_revoke_session_by_refresh_token_prevents_future_rotation() -> None:
    user = await _new_user()
    async with db_session.async_session_factory() as session:
        issued = await start_session(session, user.id)

    async with db_session.async_session_factory() as session:
        await revoke_session_by_refresh_token(session, issued.token)

    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(session, issued.token)


async def test_revoke_session_by_refresh_token_is_idempotent_for_unknown_tokens() -> None:
    # Logging out twice (or logging out with a token that was never
    # valid) must not raise — logout always looks like success to the
    # caller.
    async with db_session.async_session_factory() as session:
        await revoke_session_by_refresh_token(session, "not-a-real-token")


async def test_reuse_detection_sets_revoked_at_on_the_session_row() -> None:
    user = await _new_user()
    async with db_session.async_session_factory() as session:
        first = await start_session(session, user.id)
    async with db_session.async_session_factory() as session:
        await rotate_refresh_token(session, first.token)

    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidTokenError):
            await rotate_refresh_token(session, first.token)  # replay -> revoke

    async with db_session.async_session_factory() as session:
        stored_session = await session.get(Session, first.session_id)

    assert stored_session is not None
    assert stored_session.revoked_at is not None
