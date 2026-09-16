import base64
from uuid import uuid4

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from app.core.config import settings
from app.core.jwt_keys import build_jwks
from app.core.tokens import create_access_token


def _public_key_pem_from_jwk(jwk: dict) -> bytes:
    padded = jwk["x"] + "=" * (-len(jwk["x"]) % 4)
    raw_bytes = base64.urlsafe_b64decode(padded)
    public_key = Ed25519PublicKey.from_public_bytes(raw_bytes)
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_jwks_has_the_expected_shape() -> None:
    jwks = build_jwks()

    assert len(jwks["keys"]) == 1
    key = jwks["keys"][0]
    assert key["kty"] == "OKP"
    assert key["crv"] == "Ed25519"
    assert key["alg"] == "EdDSA"
    assert key["use"] == "sig"
    assert key["kid"] == settings.jwt_key_id
    assert "x" in key


def test_a_token_verifies_against_its_own_published_jwks() -> None:
    """The real proof JWKS works: reconstruct the public key purely from
    the published JWK — the way an external service actually would — and
    verify a freshly issued token with it. No internal key object is
    reused here.
    """
    token, _ = create_access_token(uuid4(), roles=["USER"])

    jwk = build_jwks()["keys"][0]
    reconstructed_public_key_pem = _public_key_pem_from_jwk(jwk)

    payload = jwt.decode(
        token,
        reconstructed_public_key_pem,
        algorithms=["EdDSA"],
        issuer=settings.jwt_issuer,
    )

    assert payload["roles"] == ["USER"]
