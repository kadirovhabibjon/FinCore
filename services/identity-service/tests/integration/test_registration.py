import asyncio

import pytest
from sqlalchemy import select

from app.core.exceptions import EmailAlreadyRegisteredError, PhoneAlreadyRegisteredError
from app.db import session as db_session
from app.domain.role import RoleName, UserRole
from app.services.registration import RegistrationData, register_user

pytestmark = pytest.mark.usefixtures("migrated_database")


def _data(**overrides) -> RegistrationData:
    defaults = {
        "email": "ada@example.com",
        "phone": "+998901234567",
        "password": "correct horse battery staple",
        "first_name": "Ada",
        "last_name": "Lovelace",
    }
    defaults.update(overrides)
    return RegistrationData(**defaults)


async def test_register_user_creates_user_with_hashed_password() -> None:
    async with db_session.async_session_factory() as session:
        user = await register_user(session, _data())

    assert user.id is not None
    assert user.email == "ada@example.com"
    assert user.password_hash != "correct horse battery staple"


async def test_register_user_grants_the_default_user_role() -> None:
    async with db_session.async_session_factory() as session:
        user = await register_user(session, _data())

    async with db_session.async_session_factory() as session:
        result = await session.execute(
            select(UserRole).where(UserRole.user_id == user.id)
        )
        roles = result.scalars().all()

    assert [role.role_name for role in roles] == [RoleName.USER.value]


async def test_register_user_rejects_duplicate_email() -> None:
    async with db_session.async_session_factory() as session:
        await register_user(session, _data())

    async with db_session.async_session_factory() as session:
        with pytest.raises(EmailAlreadyRegisteredError):
            await register_user(session, _data(phone="+998907654321"))


async def test_register_user_rejects_duplicate_phone() -> None:
    async with db_session.async_session_factory() as session:
        await register_user(session, _data())

    async with db_session.async_session_factory() as session:
        with pytest.raises(PhoneAlreadyRegisteredError):
            await register_user(session, _data(email="other@example.com"))


async def test_concurrent_registration_with_the_same_email_rejects_one() -> None:
    """The service-layer pre-check alone cannot prevent this: two requests
    can both pass `get_by_email` before either commits. This test proves
    the UNIQUE constraint on `users.email` is what actually decides the
    race (Section 9's "let the database constraint win" pattern, applied
    here instead of to an idempotency key).
    """

    async def attempt(phone: str) -> str:
        async with db_session.async_session_factory() as session:
            try:
                await register_user(session, _data(phone=phone))
                return "ok"
            except EmailAlreadyRegisteredError:
                return "rejected"

    results = await asyncio.gather(
        attempt("+998900000001"), attempt("+998900000002")
    )

    assert sorted(results) == ["ok", "rejected"]
