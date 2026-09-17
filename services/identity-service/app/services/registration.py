from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import EmailAlreadyRegisteredError, PhoneAlreadyRegisteredError
from app.core.security import hash_password
from app.domain.role import RoleName, UserRole
from app.domain.user import User
from app.repositories.user_repository import UserRepository


@dataclass(frozen=True)
class RegistrationData:
    email: str
    phone: str
    password: str
    first_name: str
    last_name: str


async def register_user(session: AsyncSession, data: RegistrationData) -> User:
    """Create a user and grant the default USER role, atomically.

    Duplicate email/phone is checked twice, deliberately:

    1. A pre-check via the repository gives a clean, immediate error for
       the common case (the same caller submitting twice).
    2. The UNIQUE constraint on `users.email`/`users.phone` is still the
       authoritative guard — it is what actually prevents two *concurrent*
       registrations for the same email from both succeeding (the same
       "let the database constraint win the race" pattern the spec uses
       for idempotency keys, Section 9).
    """
    repository = UserRepository(session)

    if await repository.get_by_email(data.email) is not None:
        raise EmailAlreadyRegisteredError()
    if await repository.get_by_phone(data.phone) is not None:
        raise PhoneAlreadyRegisteredError()

    user = User(
        email=data.email,
        phone=data.phone,
        password_hash=hash_password(data.password),
        first_name=data.first_name,
        last_name=data.last_name,
    )
    repository.add(user)

    try:
        await session.flush()
    except IntegrityError as exc:
        await session.rollback()
        raise _duplicate_error_for(exc) from exc

    session.add(UserRole(user_id=user.id, role_name=RoleName.USER.value))
    await session.commit()
    await session.refresh(user)
    return user


def _duplicate_error_for(
    exc: IntegrityError,
) -> EmailAlreadyRegisteredError | PhoneAlreadyRegisteredError:
    constraint = getattr(exc.orig, "constraint_name", None) or str(exc.orig)
    if "email" in constraint:
        return EmailAlreadyRegisteredError()
    if "phone" in constraint:
        return PhoneAlreadyRegisteredError()
    raise exc
