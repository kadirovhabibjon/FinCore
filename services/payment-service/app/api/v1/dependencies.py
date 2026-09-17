from dataclasses import dataclass
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fincore_common import InvalidTokenError

from app.core import auth
from app.core.fingerprint import compute_fingerprint

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class AuthenticatedUser:
    user_id: UUID
    # Kept alongside user_id so the saga can forward it to ledger-service's
    # *public* wallet endpoint to verify wallet ownership (app/services/
    # ledger.py) — reusing ledger-service's own ownership check instead
    # of duplicating it here.
    access_token: str


async def get_authenticated_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> AuthenticatedUser:
    if credentials is None:
        raise InvalidTokenError("missing bearer token")

    payload = await auth.jwt_verifier.verify(credentials.credentials)
    return AuthenticatedUser(user_id=UUID(payload["sub"]), access_token=credentials.credentials)


async def get_idempotency_fingerprint(
    request: Request,
    idempotency_key: str = Header(
        ..., alias="Idempotency-Key", min_length=1, max_length=128
    ),
) -> tuple[str, str]:
    """Returns (key, fingerprint) for app.services.idempotency. Reads the
    raw body directly (rather than depending on the endpoint's already-
    parsed Pydantic model) so the fingerprint reflects exactly what the
    client sent, byte for byte before Pydantic normalization.
    """
    body = await request.body()
    fingerprint = compute_fingerprint(request.method, request.url.path, body)
    return idempotency_key, fingerprint
