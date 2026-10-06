"""Resetting a forgotten password with a code emailed to the account.

The email address is the proof of identity: knowing someone's phone
number or email is not enough to change their password, reading their
mailbox is. Everything here is built so that the endpoints say the same
thing whether or not an account exists, and so that the 6-digit code
can't be guessed: it lives for minutes, dies after a few wrong tries,
and only a few can be requested per hour.
"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID

from fincore_common import EventType
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import InvalidResetCodeError
from app.core.security import hash_password
from app.domain.password_reset import PasswordReset
from app.domain.user import User, UserStatus
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.outbox import user_outbox_event

CODE_LENGTH = 6


@dataclass(frozen=True)
class IssuedCode:
    """What to email. Never logged, never stored."""

    email: str
    first_name: str
    code: str


def _hash(reset_id: UUID, code: str) -> str:
    return hashlib.sha256(f"{reset_id}:{code}".encode()).hexdigest()


async def _find_user(session: AsyncSession, *, email: str | None, phone: str | None) -> User | None:
    repository = UserRepository(session)
    if phone is not None:
        user = await repository.get_by_phone(phone)
    else:
        user = await repository.get_by_email(email) if email is not None else None
    # A blocked or suspended account can't sign in, so it has no use for
    # a new password - and must look exactly like no account at all.
    if user is None or user.status != UserStatus.ACTIVE:
        return None
    return user


async def request_reset(
    session: AsyncSession, *, email: str | None, phone: str | None
) -> IssuedCode | None:
    """Creates a code for the account, replacing any earlier one. Returns
    what to email, or None when nothing should be sent (no such active
    account, or it has asked too often). The caller answers the same way
    in both cases."""
    user = await _find_user(session, email=email, phone=phone)
    if user is None:
        return None

    now = datetime.now(UTC)
    recent = await session.execute(
        select(func.count())
        .select_from(PasswordReset)
        .where(
            PasswordReset.user_id == user.id,
            PasswordReset.created_at > now - timedelta(hours=1),
        )
    )
    if recent.scalar_one() >= settings.password_reset_max_requests_per_hour:
        return None

    # Only the newest code works.
    await session.execute(
        update(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .values(used_at=now)
    )
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    reset = PasswordReset(
        user_id=user.id,
        code_hash="",
        expires_at=now + timedelta(seconds=settings.password_reset_code_ttl_seconds),
    )
    session.add(reset)
    await session.flush()  # assigns reset.id, which salts the hash
    reset.code_hash = _hash(reset.id, code)
    await session.commit()
    return IssuedCode(email=user.email, first_name=user.first_name, code=code)


async def confirm_reset(
    session: AsyncSession,
    *,
    email: str | None,
    phone: str | None,
    code: str,
    new_password: str,
) -> None:
    """Sets the new password if `code` is the account's current one.
    Every failure - no account, no code, expired, used, too many tries,
    wrong digits - raises the same InvalidResetCodeError.

    On success every session of the account is revoked: whoever was
    signed in with the forgotten (or stolen) password is signed out.
    """
    user = await _find_user(session, email=email, phone=phone)
    if user is None:
        raise InvalidResetCodeError()

    now = datetime.now(UTC)
    result = await session.execute(
        select(PasswordReset)
        .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
        .order_by(PasswordReset.created_at.desc())
        .limit(1)
        .with_for_update()
    )
    reset = result.scalar_one_or_none()
    if (
        reset is None
        or reset.expires_at <= now
        or reset.attempts >= settings.password_reset_max_attempts
    ):
        raise InvalidResetCodeError()

    if not hmac.compare_digest(reset.code_hash, _hash(reset.id, code)):
        # Counted and committed before answering, under the row lock, so
        # parallel guesses can't each get a free try.
        reset.attempts += 1
        await session.commit()
        raise InvalidResetCodeError()

    reset.used_at = now
    user.password_hash = hash_password(new_password)
    revoked = await SessionRepository(session).revoke_all_for_user(user.id, now=now)
    session.add(
        user_outbox_event(
            user,
            EventType.USER_PASSWORD_CHANGED,
            actor_user_id=user.id,
            sessions_revoked=revoked,
        )
    )
    await session.commit()
