import pytest

from app.core.exceptions import InvalidCredentialsError
from app.db import session as db_session
from app.domain.user import User, UserStatus
from app.services.authentication import authenticate_user
from app.services.registration import RegistrationData, register_user

pytestmark = pytest.mark.usefixtures("migrated_database")


async def _register(**overrides) -> User:
    defaults = {
        "email": "grace@example.com",
        "phone": "+998911111111",
        "password": "hopper-compiler-1959",
        "first_name": "Grace",
        "last_name": "Hopper",
    }
    defaults.update(overrides)
    async with db_session.async_session_factory() as session:
        return await register_user(session, RegistrationData(**defaults))


async def test_authenticate_user_succeeds_with_correct_credentials() -> None:
    await _register()

    async with db_session.async_session_factory() as session:
        user = await authenticate_user(
            session, "grace@example.com", "hopper-compiler-1959"
        )

    assert user.email == "grace@example.com"


async def test_authenticate_user_rejects_wrong_password() -> None:
    await _register()

    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(session, "grace@example.com", "wrong-password")


async def test_authenticate_user_rejects_unknown_email() -> None:
    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(session, "nobody@example.com", "whatever12345")


async def test_authenticate_user_rejects_blocked_account() -> None:
    user = await _register(email="blocked@example.com", phone="+998922222222")

    async with db_session.async_session_factory() as session:
        db_user = await session.get(User, user.id)
        db_user.status = UserStatus.BLOCKED
        await session.commit()

    async with db_session.async_session_factory() as session:
        with pytest.raises(InvalidCredentialsError):
            await authenticate_user(
                session, "blocked@example.com", "hopper-compiler-1959"
            )
