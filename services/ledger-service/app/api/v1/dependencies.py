from collections.abc import Awaitable, Callable
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError

from app.core import auth
from app.core.exceptions import InsufficientRoleError

_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_id(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> UUID:
    """Verifies the bearer token against identity-service's JWKS (no
    network call to identity-service beyond the cached JWKS fetch — see
    ADR-0003) and returns the authenticated user's id.

    Reads `auth.jwt_verifier` at call time (module attribute, not a
    frozen import) so tests can swap it via
    `monkeypatch.setattr(auth, "jwt_verifier", ...)`.
    """
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    payload = await auth.jwt_verifier.verify(credentials.credentials)
    return UUID(payload["sub"])


def require_roles(*allowed: str) -> Callable[..., Awaitable[UUID]]:
    """Role check from the token's `roles` claim, as the other services'
    admin APIs do: this service can only trust the signed claim, so a
    revoked role keeps working until that access token expires
    (ADR-0006)."""

    async def _dependency(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    ) -> UUID:
        if credentials is None:
            raise InvalidTokenError("missing bearer token")
        payload = await auth.jwt_verifier.verify(credentials.credentials)
        if not set(payload.get("roles") or ()).intersection(allowed):
            raise InsufficientRoleError(f"requires one of: {', '.join(allowed)}")
        return UUID(payload["sub"])

    return _dependency
