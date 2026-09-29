from datetime import datetime
from uuid import UUID

from sqlalchemy import exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session import RefreshToken, Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session(self, session_id: UUID) -> Session | None:
        return await self._session.get(Session, session_id)

    async def list_active_for_user(self, user_id: UUID, *, now: datetime) -> list[Session]:
        """Most recently used first. "Active" means refreshable right now:
        not revoked, with an unused refresh token that hasn't expired —
        a session whose last token simply lapsed is not listed, since
        nothing could use it anymore."""
        refreshable = exists().where(
            RefreshToken.session_id == Session.id,
            RefreshToken.used_at.is_(None),
            RefreshToken.expires_at > now,
        )
        result = await self._session.execute(
            select(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None), refreshable)
            .order_by(Session.last_used_at.desc().nulls_last(), Session.created_at.desc())
        )
        return list(result.scalars().all())

    async def revoke_all_for_user(
        self, user_id: UUID, *, now: datetime, except_session_id: UUID | None = None
    ) -> int:
        query = update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        if except_session_id is not None:
            query = query.where(Session.id != except_session_id)
        result = await self._session.execute(query.values(revoked_at=now))
        return result.rowcount  # type: ignore[attr-defined]

    async def get_refresh_token_by_hash(self, token_hash: str) -> RefreshToken | None:
        result = await self._session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        )
        return result.scalar_one_or_none()

    async def mark_used_if_unused(self, refresh_token_id: UUID) -> bool:
        """Atomically claims a refresh token for rotation.

        The WHERE clause is the guard: if two requests race to redeem the
        same token, exactly one UPDATE matches a row (rowcount == 1); the
        loser gets rowcount == 0 and the caller treats that as reuse, the
        same "database constraint decides the race" pattern used for
        registration (Section 9's idempotency-key guidance, applied here).
        """
        result = await self._session.execute(
            update(RefreshToken)
            .where(RefreshToken.id == refresh_token_id, RefreshToken.used_at.is_(None))
            .values(used_at=func.now())
        )
        # `.rowcount` is on CursorResult, not the abstract Result[Any] that
        # execute()'s type stub returns — it's always a CursorResult here
        # at runtime because this is an UPDATE, not a plain SELECT.
        return result.rowcount == 1  # type: ignore[attr-defined]
