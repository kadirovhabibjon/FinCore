from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError

from app.core import auth
from app.core.exceptions import InsufficientRoleError

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    roles: frozenset[str] = frozenset()


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    payload = await auth.jwt_verifier.verify(credentials.credentials)
    return AuthenticatedUser(
        user_id=UUID(payload["sub"]), roles=frozenset(payload.get("roles") or ())
    )


def require_roles(*allowed: str) -> Callable[..., Awaitable[AuthenticatedUser]]:
    """Role check from the token's `roles` claim — the same trust model,
    and the same caveat, as payment-service's `require_roles`: a revoked
    role keeps working until that access token expires (ADR-0006).
    """

    async def _dependency(
        user: AuthenticatedUser = Depends(get_authenticated_user),
    ) -> AuthenticatedUser:
        if user.roles.isdisjoint(allowed):
            raise InsufficientRoleError(f"requires one of: {', '.join(sorted(allowed))}")
        return user

    return _dependency
