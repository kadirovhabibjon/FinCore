from datetime import UTC, datetime
from uuid import UUID

from fincore_common import EventType
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IncorrectPasswordError, PasswordUnchangedError
from app.core.security import hash_password, verify_password
from app.domain.user import User
from app.repositories.session_repository import SessionRepository
from app.services.outbox import user_outbox_event


async def change_password(
    session: AsyncSession,
    user: User,
    *,
    current_session_id: UUID | None,
    current_password: str,
    new_password: str,
) -> int:
    """Changes the caller's password (spec Section 18's PASSWORD_CHANGED).

    Every *other* session is revoked in the same transaction — whoever
    may have learned the old password loses whatever they signed in
    with — while the device making the change stays signed in. The audit
    event is written in that transaction too. Returns how many sessions
    were revoked.
    """
    if not verify_password(current_password, user.password_hash):
        raise IncorrectPasswordError()
    if verify_password(new_password, user.password_hash):
        raise PasswordUnchangedError("the new password must differ from the current one")

    user.password_hash = hash_password(new_password)
    revoked = await SessionRepository(session).revoke_all_for_user(
        user.id, now=datetime.now(UTC), except_session_id=current_session_id
    )
    session.add(
        user_outbox_event(
            user,
            EventType.USER_PASSWORD_CHANGED,
            actor_user_id=user.id,
            sessions_revoked=revoked,
        )
    )
    await session.commit()
    return revoked
