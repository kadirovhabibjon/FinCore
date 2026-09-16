import base64

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from app.core.config import settings


def _normalize_pem(raw: str) -> bytes:
    # A .env file can hold a real multi-line PEM directly; container
    # orchestrators that only support single-line env values need the
    # newlines escaped as literal "\n" instead. Support both.
    return raw.replace("\\n", "\n").encode("utf-8")


def _load_private_key() -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(
        _normalize_pem(settings.jwt_private_key), password=None
    )
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("JWT_PRIVATE_KEY must be an Ed25519 private key")
    return key


private_key: Ed25519PrivateKey = _load_private_key()
public_key: Ed25519PublicKey = private_key.public_key()

private_key_pem: bytes = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
)
public_key_pem: bytes = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def build_jwks() -> dict:
    """The public half of the signing key, as a JSON Web Key Set.

    Any service can fetch this and verify a FinCore-issued JWT locally,
    without calling back into identity-service per request (Section 5:
    "other services verify with the public key via JWKS").
    """
    raw_public_bytes = public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url(raw_public_bytes),
                "kid": settings.jwt_key_id,
                "use": "sig",
                "alg": "EdDSA",
            }
        ]
    }
