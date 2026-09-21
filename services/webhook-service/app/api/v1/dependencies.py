from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError

from app.core import auth

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    payload = await auth.jwt_verifier.verify(credentials.credentials)
    return AuthenticatedUser(user_id=UUID(payload["sub"]))
