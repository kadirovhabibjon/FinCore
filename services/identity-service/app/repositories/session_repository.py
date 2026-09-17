from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.session import RefreshToken, Session


class SessionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_session(self, session_id: UUID) -> Session | None:
        return await self._session.get(Session, session_id)

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
        return result.rowcount == 1
