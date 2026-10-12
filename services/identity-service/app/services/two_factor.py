"""Two-step sign-in: after the password, a 6-digit code emailed to the
account.

The password proves the account's secret is known; the code proves its
mailbox can be read. A stolen password alone no longer signs anyone in.

A code is asked for with a *challenge*: the id of the code's own row,
random, given only to whoever has just passed the password step. Six
digits are guessable in a million tries; a challenge is not guessable
at all, and each one takes five wrong codes before it dies. So the
digits protect against someone reading over a shoulder, the challenge
against someone guessing from afar.

Turning it on takes a code too, so an account can never be locked
behind a mailbox that doesn't work.
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
from app.core.exceptions import (
    IncorrectPasswordError,
    InvalidLoginCodeError,
    TooManyCodesError,
    TwoFactorUnavailableError,
)
from app.core.security import verify_password
from app.domain.login_code import CodePurpose, LoginCode
from app.domain.user import User, UserStatus
from app.services import mailer
from app.services.outbox import user_outbox_event

CODE_LENGTH = 6


@dataclass(frozen=True)
class Challenge:
    """What the client is told, and what to email. The code is never
    logged, stored or returned to the client."""

    id: UUID
    code: str
    email: str
    first_name: str
    expires_in: int


def _hash(code_id: UUID, code: str) -> str:
    return hashlib.sha256(f"{code_id}:{code}".encode()).hexdigest()


def email_hint(email: str) -> str:
    """"az***@gmail.com": enough to know which mailbox to open, not
    enough to learn an address from a password alone."""
    local, _, domain = email.partition("@")
    return f"{local[:2]}***@{domain}"


def check_can_send(user: User) -> None:
    """A code that can't arrive must never become the only way in."""
    if not mailer.is_configured() or not mailer.is_deliverable(user.email):
        raise TwoFactorUnavailableError(
            "A code can't be emailed to this account right now."
        )


async def issue_code(session: AsyncSession, user: User, purpose: CodePurpose) -> Challenge:
    """Creates a code for the account, replacing any earlier one of the
    same purpose. At most a few per hour: each is an email, and each is
    five more guesses."""
    check_can_send(user)
    now = datetime.now(UTC)
    recent = await session.execute(
        select(func.count())
        .select_from(LoginCode)
        .where(LoginCode.user_id == user.id, LoginCode.created_at > now - timedelta(hours=1))
    )
    if recent.scalar_one() >= settings.login_code_max_requests_per_hour:
        raise TooManyCodesError("Too many codes were sent. Try again in an hour.")

    await session.execute(
        update(LoginCode)
        .where(
            LoginCode.user_id == user.id,
            LoginCode.purpose == purpose,
            LoginCode.used_at.is_(None),
        )
        .values(used_at=now)
    )
    code = "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))
    record = LoginCode(
        user_id=user.id,
        purpose=purpose,
        code_hash="",
        expires_at=now + timedelta(seconds=settings.login_code_ttl_seconds),
    )
    session.add(record)
    await session.flush()  # assigns record.id, which salts the hash
    record.code_hash = _hash(record.id, code)
    await session.commit()
    return Challenge(
        id=record.id,
        code=code,
        email=user.email,
        first_name=user.first_name,
        expires_in=settings.login_code_ttl_seconds,
    )


async def redeem_code(
    session: AsyncSession,
    challenge_id: UUID,
    code: str,
    purpose: CodePurpose,
    *,
    user_id: UUID | None = None,
) -> User:
    """The account the code was issued to, if `code` is right. Every
    failure raises the same InvalidLoginCodeError. `user_id`, when given,
    must be the code's owner (turning two-step sign-in on: the caller is
    already signed in, and may only confirm their own)."""
    result = await session.execute(
        select(LoginCode).where(LoginCode.id == challenge_id).with_for_update()
    )
    record = result.scalar_one_or_none()
    now = datetime.now(UTC)
    if (
        record is None
        or record.purpose != purpose
        or record.used_at is not None
        or record.expires_at <= now
        or record.attempts >= settings.login_code_max_attempts
        or (user_id is not None and record.user_id != user_id)
    ):
        raise InvalidLoginCodeError()

    if not hmac.compare_digest(record.code_hash, _hash(record.id, code)):
        # Counted and committed before answering, under the row lock, so
        # parallel guesses can't each get a free try.
        record.attempts += 1
        await session.commit()
        raise InvalidLoginCodeError()

    user = await session.get(User, record.user_id)
    # Blocked or suspended between the password and the code.
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidLoginCodeError()
    record.used_at = now
    await session.commit()
    return user


def _require_password(user: User, password: str) -> None:
    if not verify_password(password, user.password_hash):
        raise IncorrectPasswordError("the current password is wrong")


async def begin_enabling(session: AsyncSession, user: User, current_password: str) -> Challenge:
    _require_password(user, current_password)
    return await issue_code(session, user, CodePurpose.ENABLE)


async def _set_enabled(
    session: AsyncSession, user: User, enabled: bool, actor: UUID | None
) -> None:
    if user.two_factor_enabled == enabled:
        return
    user.two_factor_enabled = enabled
    session.add(
        user_outbox_event(
            user, EventType.USER_PROFILE_UPDATED, actor_user_id=actor, changed_fields="two_factor"
        )
    )
    await session.commit()


async def confirm_enabling(
    session: AsyncSession, user: User, challenge_id: UUID, code: str
) -> None:
    confirmed = await redeem_code(
        session, challenge_id, code, CodePurpose.ENABLE, user_id=user.id
    )
    await _set_enabled(session, confirmed, True, actor=user.id)


async def disable(session: AsyncSession, user: User, current_password: str) -> None:
    """Needs the password even though the caller is signed in: a
    borrowed unlocked device must not be able to take the second step
    away."""
    _require_password(user, current_password)
    await _set_enabled(session, user, False, actor=user.id)


async def disable_by_operator(session: AsyncSession, user: User) -> None:
    """For someone locked out of their mailbox, from the operator CLI
    after their identity was checked some other way."""
    await _set_enabled(session, user, False, actor=None)
