from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import jwt

from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.jwt_keys import private_key_pem, public_key_pem

ALGORITHM = "EdDSA"


def create_access_token(user_id: UUID, roles: list[str]) -> tuple[str, datetime]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.jwt_access_token_ttl_seconds)

    payload = {
        "sub": str(user_id),
        "iss": settings.jwt_issuer,
        "iat": now,
        "exp": expires_at,
        "roles": roles,
    }
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
