from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.jwt_keys import private_key_pem, public_key_pem

ALGORITHM = "EdDSA"


def create_access_token(
    user_id: UUID, roles: list[str], *, session_id: UUID | None = None
) -> tuple[str, datetime]:
    now = datetime.now(UTC)
    expires_at = now + timedelta(seconds=settings.jwt_access_token_ttl_seconds)

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": expires_at,
        "roles": roles,
    }
    if session_id is not None:
        # Which login session minted this token — lets the user's own
        # sessions list mark "this device" and keeps a user from revoking
        # the session they're using by accident. Not an authorization
        # input anywhere.
        payload["sid"] = str(session_id)
    token = jwt.encode(
        payload,
        private_key_pem,
        algorithm=ALGORITHM,
        headers={"kid": settings.jwt_key_id},
    )
    return token, expires_at


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        return jwt.decode(
            token,
            public_key_pem,
            algorithms=[ALGORITHM],
            issuer=settings.jwt_issuer,
        )
    except jwt.PyJWTError as exc:
        raise InvalidTokenError(str(exc)) from exc
