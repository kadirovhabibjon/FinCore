from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CannotChangeOwnStatusError, UserNotFoundError
from app.domain.user import User, UserStatus
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.outbox import STATUS_EVENTS, user_outbox_event


async def change_user_status(
    session: AsyncSession, *, actor_id: UUID, user_id: UUID, new_status: UserStatus
) -> User:
    """Admin status management (spec Section 5: ACTIVE / BLOCKED /
    SUSPENDED). Leaving ACTIVE revokes every open session in the same
    call, so the account can't refresh its way back to a fresh access
    token; login is already refused for any non-ACTIVE account. Access
    tokens issued before the change stay valid until they expire —
    bounded by the short access-token TTL, the same trade-off noted in
    `get_auth_context`.
    """
    if actor_id == user_id:
        raise CannotChangeOwnStatusError(str(user_id))

    user = await UserRepository(session).get_by_id(user_id)
    if user is None:
        raise UserNotFoundError(str(user_id))

    previous_status = user.status
    if previous_status == new_status:
        return user  # nothing changed, so nothing to revoke or audit

    user.status = new_status
    if new_status != UserStatus.ACTIVE:
        # Same transaction as the status change: never a blocked account
        # with sessions still open, even briefly.
        await SessionRepository(session).revoke_all_for_user(user.id, now=datetime.now(UTC))
    # ...and the audit event too (spec Section 18: an action that
    # committed can't silently lose its audit record).
    session.add(
        user_outbox_event(
            user,
            STATUS_EVENTS[new_status],
            actor_user_id=actor_id,
            previous_status=previous_status.value,
        )
    )
    await session.commit()
    await session.refresh(user)
    return user
