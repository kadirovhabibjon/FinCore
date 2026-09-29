from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession as DbSession

from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.security import generate_refresh_token, hash_refresh_token
from app.domain.session import RefreshToken, Session
from app.domain.user import UserStatus
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class IssuedRefreshToken:
    session_id: UUID
    user_id: UUID
    token: str
    expires_at: datetime


async def start_session(
    db: DbSession,
    user_id: UUID,
    *,
    user_agent: str | None = None,
    ip_address: str | None = None,
) -> IssuedRefreshToken:
    """Called on login: opens a new session and issues its first refresh
    token."""
    session = Session(
        user_id=user_id,
        user_agent=user_agent[:255] if user_agent else None,
        ip_address=ip_address[:64] if ip_address else None,
        last_used_at=datetime.now(UTC),
    )
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

    if stored.expires_at < datetime.now(UTC):
        raise InvalidTokenError("refresh token expired")

    claimed = await repository.mark_used_if_unused(stored.id)
    if not claimed:
        session.revoked_at = datetime.now(UTC)
        await db.commit()
        raise InvalidTokenError("refresh token reuse detected")

    # A blocked or suspended account must not be able to keep minting
    # access tokens from a session opened before the status change.
    user = await UserRepository(db).get_by_id(session.user_id)
    if user is None or user.status != UserStatus.ACTIVE:
        session.revoked_at = datetime.now(UTC)
        await db.commit()
        raise InvalidTokenError("session owner is not an active user")

    session.last_used_at = datetime.now(UTC)
    issued = await _issue_refresh_token(db, session.id, session.user_id)
    await db.commit()
    return issued


async def list_active_sessions(db: DbSession, user_id: UUID) -> list[Session]:
    """Sessions a user could still refresh from: not revoked, and holding
    at least one refresh token that is unused and unexpired."""
    return await SessionRepository(db).list_active_for_user(user_id, now=datetime.now(UTC))


async def revoke_user_session(db: DbSession, user_id: UUID, session_id: UUID) -> bool:
    """Revokes one of the caller's own sessions. Returns False when it
    doesn't exist or belongs to someone else — the caller turns both into
    the same 404, never revealing another user's session ids. Revoking an
    already-revoked session is a no-op success (idempotent, like logout).
    """
    session = await SessionRepository(db).get_session(session_id)
    if session is None or session.user_id != user_id:
        return False
    if session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        await db.commit()
    return True


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
        session.revoked_at = datetime.now(UTC)
        await db.commit()


async def _issue_refresh_token(
    db: DbSession, session_id: UUID, user_id: UUID
) -> IssuedRefreshToken:
    plaintext = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(
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
