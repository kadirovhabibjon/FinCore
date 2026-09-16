from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidCredentialsError
from app.core.security import verify_password
from app.domain.user import User, UserStatus
from app.repositories.user_repository import UserRepository


async def authenticate_user(session: AsyncSession, email: str, password: str) -> User:
    """Verify credentials and return the user, or raise InvalidCredentialsError.

    Used by the login endpoint (added once JWT issuance exists). Kept
    separate from token issuance so credential-checking logic has its own
    focused tests independent of how the resulting session is represented.
    """
    repository = UserRepository(session)
    user = await repository.get_by_email(email)

    if user is None or not verify_password(password, user.password_hash):
        raise InvalidCredentialsError()

    if user.status != UserStatus.ACTIVE:
        raise InvalidCredentialsError()

    return user
