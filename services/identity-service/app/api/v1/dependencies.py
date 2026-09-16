from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InvalidTokenError
from app.core.tokens import decode_access_token
from app.db.session import get_db
from app.domain.user import User, UserStatus
from app.repositories.user_repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    payload = decode_access_token(credentials.credentials)
    user = await UserRepository(session).get_by_id(UUID(payload["sub"]))

    # A token can outlive a status change (e.g. an admin blocking the
    # account) until it expires — acceptable for the short-lived access
    # token TTL configured here, but this is exactly why the TTL is short
    # rather than left unbounded.
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidTokenError("token subject is not an active user")

    return user
