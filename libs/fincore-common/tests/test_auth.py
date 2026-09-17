import base64
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import Depends, FastAPI
from starlette.testclient import TestClient

from fincore_common.auth import InvalidTokenError, JWTVerifier, require_internal_token
from fincore_common.errors import register_error_handlers

_ISSUER = "fincore-identity-service"
_KEY_ID = "test-key-1"


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture
def keypair():
    private_key = Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    raw_public = public_key.public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url(raw_public),
                "kid": _KEY_ID,
                "use": "sig",
                "alg": "EdDSA",
            }
        ]
    }
    return private_pem, jwks


def _sign(
    private_pem: bytes, *, issuer: str = _ISSUER, expires_delta: timedelta | None = None
) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": "11111111-1111-1111-1111-111111111111",
        "iss": issuer,
        "iat": now,
        "exp": now + (expires_delta or timedelta(minutes=15)),
        "roles": ["USER"],
    }
    return jwt.encode(payload, private_pem, algorithm="EdDSA", headers={"kid": _KEY_ID})


def _jwks_transport(jwks: dict) -> httpx.ASGITransport:
    app = FastAPI()

    @app.get("/.well-known/jwks.json")
    async def _jwks() -> dict:
        return jwks

    return httpx.ASGITransport(app=app)


async def test_verify_accepts_a_validly_signed_token(keypair) -> None:
    private_pem, jwks = keypair
    token = _sign(private_pem)
    verifier = JWTVerifier(
        jwks_url="http://identity/.well-known/jwks.json",
        issuer=_ISSUER,
        transport=_jwks_transport(jwks),
    )

    payload = await verifier.verify(token)

    assert payload["sub"] == "11111111-1111-1111-1111-111111111111"
    assert payload["roles"] == ["USER"]


async def test_verify_rejects_wrong_issuer(keypair) -> None:
    private_pem, jwks = keypair
    token = _sign(private_pem, issuer="someone-else")
    verifier = JWTVerifier(
        jwks_url="http://identity/.well-known/jwks.json",
        issuer=_ISSUER,
        transport=_jwks_transport(jwks),
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_verify_rejects_expired_token(keypair) -> None:
    private_pem, jwks = keypair
    token = _sign(private_pem, expires_delta=timedelta(minutes=-1))
    verifier = JWTVerifier(
        jwks_url="http://identity/.well-known/jwks.json",
        issuer=_ISSUER,
        transport=_jwks_transport(jwks),
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


async def test_verify_rejects_a_tampered_token(keypair) -> None:
    private_pem, jwks = keypair
    token = _sign(private_pem)
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
    verifier = JWTVerifier(
        jwks_url="http://identity/.well-known/jwks.json",
        issuer=_ISSUER,
        transport=_jwks_transport(jwks),
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(tampered)


async def test_verify_rejects_a_token_from_an_unknown_key_id(keypair) -> None:
    _, jwks = keypair
    other_private_key = Ed25519PrivateKey.generate()
    other_pem = other_private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    # Signed with a key whose kid isn't in the JWKS response at all.
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": "x", "iss": _ISSUER, "iat": now, "exp": now + timedelta(minutes=5)},
        other_pem,
        algorithm="EdDSA",
        headers={"kid": "some-other-key"},
    )
    verifier = JWTVerifier(
        jwks_url="http://identity/.well-known/jwks.json",
        issuer=_ISSUER,
        transport=_jwks_transport(jwks),
    )

    with pytest.raises(InvalidTokenError):
        await verifier.verify(token)


def _build_internal_app(expected_token: str) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/internal/v1/ping", dependencies=[Depends(require_internal_token(expected_token))])
    async def _ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_require_internal_token_accepts_the_correct_token() -> None:
    client = TestClient(_build_internal_app("secret-123"))

    response = client.get("/internal/v1/ping", headers={"X-Internal-Token": "secret-123"})

    assert response.status_code == 200


def test_require_internal_token_rejects_the_wrong_token() -> None:
    client = TestClient(_build_internal_app("secret-123"), raise_server_exceptions=False)

    response = client.get("/internal/v1/ping", headers={"X-Internal-Token": "wrong"})

    assert response.status_code == 403
    assert response.json()["title"] == "Invalid Internal Service Token"


def test_require_internal_token_rejects_a_missing_header() -> None:
    client = TestClient(_build_internal_app("secret-123"), raise_server_exceptions=False)

    response = client.get("/internal/v1/ping")

    assert response.status_code == 422  # FastAPI's own required-header validation
