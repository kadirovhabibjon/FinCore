"""A customer editing their own profile: name, email address, phone."""

from dataclasses import dataclass
from datetime import UTC, datetime

from fincore_common import EventType
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    CurrentPasswordRequiredError,
    EmailAlreadyRegisteredError,
    IncorrectPasswordError,
    PhoneAlreadyRegisteredError,
)
from app.core.security import verify_password
from app.domain.password_reset import PasswordReset
from app.domain.user import User
from app.repositories.user_repository import UserRepository
from app.services.outbox import user_outbox_event

# Fixed order, so the audit event reads the same for the same change.
_FIELDS = ("first_name", "last_name", "email", "phone")
# How the account is signed in to and recovered.
_SENSITIVE = frozenset({"email", "phone"})


@dataclass(frozen=True)
class ProfileChange:
    """What an update actually changed, and the address to tell about it."""

    changed: tuple[str, ...]
    # Where the account's mail went before this update.
    previous_email: str


async def update_profile(
    session: AsyncSession,
    user: User,
    *,
    first_name: str | None = None,
    last_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    current_password: str | None = None,
) -> ProfileChange:
    """Applies the fields that differ from what is stored; values equal
    to the current ones, and fields left out, change nothing.

    A new email or phone needs the current password and must not belong
    to another account. Changing the email also cancels any password
    reset code already sent: it went to the old address.
    """
    wanted = {"first_name": first_name, "last_name": last_name, "email": email, "phone": phone}
    changed = tuple(
        field
        for field in _FIELDS
        if wanted[field] is not None and wanted[field] != getattr(user, field)
    )
    previous_email = user.email
    if not changed:
        return ProfileChange(changed=(), previous_email=previous_email)

    if _SENSITIVE.intersection(changed):
        if current_password is None:
            raise CurrentPasswordRequiredError(
                "Enter your current password to change your email or phone number."
            )
        if not verify_password(current_password, user.password_hash):
            raise IncorrectPasswordError()

    # Friendly pre-checks; the UNIQUE constraints below are what actually
    # decide when two people ask for the same value at once.
    repository = UserRepository(session)
    if "email" in changed and await repository.get_by_email(wanted["email"] or "") is not None:
        raise EmailAlreadyRegisteredError()
    if "phone" in changed and await repository.get_by_phone(wanted["phone"] or "") is not None:
        raise PhoneAlreadyRegisteredError()

    for field in changed:
        setattr(user, field, wanted[field])
    if "email" in changed:
        await session.execute(
            update(PasswordReset)
            .where(PasswordReset.user_id == user.id, PasswordReset.used_at.is_(None))
            .values(used_at=datetime.now(UTC))
        )
    session.add(
        user_outbox_event(
            user,
            EventType.USER_PROFILE_UPDATED,
            actor_user_id=user.id,
            changed_fields=",".join(changed),
        )
    )
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        constraint = getattr(exc.orig, "constraint_name", None) or str(exc.orig)
        if "email" in constraint:
            raise EmailAlreadyRegisteredError() from exc
        if "phone" in constraint:
            raise PhoneAlreadyRegisteredError() from exc
        raise
    await session.refresh(user)
    return ProfileChange(changed=changed, previous_email=previous_email)
