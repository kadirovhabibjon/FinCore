from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.core.config import settings
from app.core.exceptions import InvalidTokenError
from app.core.tokens import ALGORITHM, create_access_token, decode_access_token


def test_create_access_token_round_trips_through_decode() -> None:
    user_id = uuid4()
    token, expires_at = create_access_token(user_id, roles=["USER"])

    payload = decode_access_token(token)

    assert payload["sub"] == str(user_id)
    assert payload["roles"] == ["USER"]
    assert payload["iss"] == settings.jwt_issuer
    assert isinstance(expires_at, datetime)


def test_decode_access_token_rejects_a_tampered_token() -> None:
    token, _ = create_access_token(uuid4(), roles=["USER"])
    tampered = token[:-1] + ("a" if token[-1] != "a" else "b")

    with pytest.raises(InvalidTokenError):
        decode_access_token(tampered)


def test_decode_access_token_rejects_an_expired_token() -> None:
    now = datetime.now(timezone.utc)
    expired_payload = {
        "sub": str(uuid4()),
        "iss": settings.jwt_issuer,
        "iat": now - timedelta(hours=1),
        "exp": now - timedelta(minutes=1),
        "roles": ["USER"],
    }
    from app.core.jwt_keys import private_key_pem

    expired_token = jwt.encode(expired_payload, private_key_pem, algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(expired_token)


def test_decode_access_token_rejects_wrong_issuer() -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(uuid4()),
        "iss": "someone-else",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "roles": ["USER"],
    }
    from app.core.jwt_keys import private_key_pem

    token = jwt.encode(payload, private_key_pem, algorithm=ALGORITHM)

    with pytest.raises(InvalidTokenError):
        decode_access_token(token)


def test_create_access_token_sets_the_configured_key_id_header() -> None:
    token, _ = create_access_token(uuid4(), roles=["USER"])

    header = jwt.get_unverified_header(token)

    assert header["kid"] == settings.jwt_key_id
    assert header["alg"] == ALGORITHM
