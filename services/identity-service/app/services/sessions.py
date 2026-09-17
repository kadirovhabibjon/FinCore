from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession as DbSession

from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.security import generate_refresh_token, hash_refresh_token
from app.domain.session import RefreshToken, Session
from app.repositories.session_repository import SessionRepository


@dataclass(frozen=True)
class IssuedRefreshToken:
    session_id: UUID
    user_id: UUID
    token: str
    expires_at: datetime


async def start_session(db: DbSession, user_id: UUID) -> IssuedRefreshToken:
    """Called on login: opens a new session and issues its first refresh
    token."""
    session = Session(user_id=user_id)
    db.add(session)
    await db.flush()  # assign session.id before the refresh token references it

    issued = await _issue_refresh_token(db, session.id, user_id)
    await db.commit()
    return issued


async def rotate_refresh_token(db: DbSession, presented_token: str) -> IssuedRefreshToken:
    """Exchanges a valid, unused refresh token for a new one.

    Reuse of an already-rotated token — whether a genuine replay attack or
    two concurrent requests racing to redeem the same token — revokes the
    entire session: Section 5's "reusing an old refresh token revokes the
    whole session family."
    """
    repository = SessionRepository(db)
    token_hash = hash_refresh_token(presented_token)

    stored = await repository.get_refresh_token_by_hash(token_hash)
    if stored is None:
        raise InvalidTokenError("unknown refresh token")

    session = await repository.get_session(stored.session_id)
    if session is None or session.revoked_at is not None:
        raise InvalidTokenError("session revoked")

    if stored.expires_at < datetime.now(timezone.utc):
        raise InvalidTokenError("refresh token expired")

    claimed = await repository.mark_used_if_unused(stored.id)
    if not claimed:
        session.revoked_at = datetime.now(timezone.utc)
        await db.commit()
        raise InvalidTokenError("refresh token reuse detected")

    issued = await _issue_refresh_token(db, session.id, session.user_id)
    await db.commit()
    return issued


async def revoke_session_by_refresh_token(db: DbSession, presented_token: str) -> None:
    """Logout. Idempotent: an unknown or already-revoked token is treated
    as "already logged out" rather than an error — a client retrying a
    logout call should never see a failure."""
    repository = SessionRepository(db)
    stored = await repository.get_refresh_token_by_hash(hash_refresh_token(presented_token))
    if stored is None:
        return

    session = await repository.get_session(stored.session_id)
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        await db.commit()


async def _issue_refresh_token(
    db: DbSession, session_id: UUID, user_id: UUID
) -> IssuedRefreshToken:
    plaintext = generate_refresh_token()
    expires_at = datetime.now(timezone.utc) + timedelta(
        seconds=settings.refresh_token_ttl_seconds
    )

    db.add(
        RefreshToken(
            session_id=session_id,
            token_hash=hash_refresh_token(plaintext),
            expires_at=expires_at,
        )
    )
    return IssuedRefreshToken(
        session_id=session_id, user_id=user_id, token=plaintext, expires_at=expires_at
    )
