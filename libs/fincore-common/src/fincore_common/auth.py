import base64
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import Header, status

from .errors import DomainError


class InvalidTokenError(DomainError):
    status_code = status.HTTP_401_UNAUTHORIZED
    title = "Invalid Token"


class InvalidInternalTokenError(DomainError):
    status_code = status.HTTP_403_FORBIDDEN
    title = "Invalid Internal Service Token"


def _public_key_pem_from_jwk(jwk: dict[str, Any]) -> bytes:
    if jwk.get("kty") != "OKP" or jwk.get("crv") != "Ed25519":
        raise InvalidTokenError(f"unsupported JWK kty/crv: {jwk.get('kty')}/{jwk.get('crv')}")
    padded = jwk["x"] + "=" * (-len(jwk["x"]) % 4)
    raw_bytes = base64.urlsafe_b64decode(padded)
    public_key = Ed25519PublicKey.from_public_bytes(raw_bytes)
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


class JWTVerifier:
    """Verifies a JWT issued by identity-service, using its published
    JWKS — no network call to identity-service per request (Section 5).

    The JWKS response is fetched over HTTP and cached in memory, keyed by
    `kid`, for `cache_ttl_seconds`. This is deliberately *not* built on
    PyJWT's own `PyJWKClient`: that client fetches synchronously (via
    `urllib`), which would block the whole event loop if awaited from
    inside an async FastAPI dependency. This class uses `httpx.AsyncClient`
    instead, so a cache-miss fetch doesn't stall every other in-flight
    request on the same worker.
    """

    def __init__(
        self,
        jwks_url: str,
        issuer: str,
        algorithm: str = "EdDSA",
        cache_ttl_seconds: float = 300.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._jwks_url = jwks_url
        self._issuer = issuer
        self._algorithm = algorithm
        self._cache_ttl_seconds = cache_ttl_seconds
        self._transport = transport
        self._cached_keys: dict[str, bytes] = {}
        self._cached_at: float = 0.0

    async def verify(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        public_key_pem = await self._get_key(header.get("kid"))

        try:
            return jwt.decode(
                token, public_key_pem, algorithms=[self._algorithm], issuer=self._issuer
            )
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

    async def _get_key(self, kid: str | None) -> bytes:
        stale = (time.monotonic() - self._cached_at) > self._cache_ttl_seconds
        if kid not in self._cached_keys or stale:
            await self._refresh()
        try:
            return self._cached_keys[kid]  # type: ignore[index]
        except KeyError:
            raise InvalidTokenError(f"unknown signing key id: {kid!r}") from None

    async def _refresh(self) -> None:
        async with httpx.AsyncClient(timeout=5.0, transport=self._transport) as client:
            response = await client.get(self._jwks_url)
            response.raise_for_status()
            jwks = response.json()

        self._cached_keys = {
            jwk["kid"]: _public_key_pem_from_jwk(jwk)
            for jwk in jwks.get("keys", [])
            if "kid" in jwk
        }
        self._cached_at = time.monotonic()


def require_internal_token(expected_token: str) -> Callable[..., Awaitable[None]]:
    """FastAPI dependency factory for `/internal/*` endpoints (Section 19:
    service-to-service authentication). A shared secret compared against
    the `X-Internal-Token` header is enough for v1 — mTLS is explicitly a
    later concern per the spec.
    """

    async def _dependency(x_internal_token: str = Header(...)) -> None:
        if x_internal_token != expected_token:
            raise InvalidInternalTokenError("internal service token mismatch")

    return _dependency
