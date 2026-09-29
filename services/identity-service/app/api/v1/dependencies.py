from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import InsufficientRoleError, InvalidTokenError
from app.core.tokens import decode_access_token
from app.db.session import get_db
from app.domain.role import RoleName
from app.domain.user import User, UserStatus
from app.repositories.user_repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthContext:
    user: User
    # Read from the database, not the token: identity-service owns roles,
    # so a revoked role takes effect here immediately rather than when the
    # caller's access token expires.
    roles: frozenset[str]
    # The login session that minted the token (its `sid` claim), if any.
    session_id: UUID | None


async def get_auth_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> AuthContext:
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    payload = decode_access_token(credentials.credentials)
    repository = UserRepository(session)
    user = await repository.get_by_id(UUID(payload["sub"]))

    # A token can outlive a status change (e.g. an admin blocking the
    # account) until it expires — acceptable for the short-lived access
    # token TTL configured here, but this is exactly why the TTL is short
    # rather than left unbounded.
    if user is None or user.status != UserStatus.ACTIVE:
        raise InvalidTokenError("token subject is not an active user")

    roles = frozenset(await repository.get_role_names(user.id))
    sid = payload.get("sid")
    return AuthContext(user=user, roles=roles, session_id=UUID(sid) if sid else None)


async def get_current_user(context: AuthContext = Depends(get_auth_context)) -> User:
    return context.user


def require_roles(*allowed: RoleName) -> Callable[..., Awaitable[AuthContext]]:
    """Dependency factory: the caller must hold at least one of `allowed`
    (spec Section 5's RBAC). A missing or invalid token is still a 401;
    a valid token without the role is a 403."""
    allowed_names = frozenset(role.value for role in allowed)

    async def _dependency(context: AuthContext = Depends(get_auth_context)) -> AuthContext:
        if not context.roles & allowed_names:
            raise InsufficientRoleError(f"requires one of: {', '.join(sorted(allowed_names))}")
        return context

    return _dependency
