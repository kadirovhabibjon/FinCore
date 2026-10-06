import asyncio
import base64
import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import httpx
import jwt
import pytest
from alembic import command
from alembic.config import Config
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fincore_common import JWTVerifier
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.kafka import KafkaContainer
from testcontainers.community.postgres import PostgresContainer

from app.core import auth as auth_module
from app.core.config import settings
from app.db import session as db_session


@pytest.fixture(scope="module")
def postgres_url() -> str:
    with PostgresContainer("postgres:16-alpine", driver="asyncpg") as postgres:
        yield postgres.get_connection_url()


@pytest.fixture
def migrated_database(postgres_url: str, monkeypatch: pytest.MonkeyPatch):
    """Runs Alembic migrations against a fresh schema in the module's
    PostgreSQL testcontainer, then points the app's DB session machinery
    at it, so repositories/services under test hit a real, migrated
    database instead of the process's configured one.
    """
    monkeypatch.setattr(settings, "database_url", postgres_url)
    alembic_config = Config("alembic.ini")
    command.upgrade(alembic_config, "head")

    test_engine = create_async_engine(postgres_url, pool_pre_ping=True)
    test_session_factory = async_sessionmaker(test_engine, expire_on_commit=False)
    monkeypatch.setattr(db_session, "engine", test_engine)
    monkeypatch.setattr(db_session, "async_session_factory", test_session_factory)

    yield test_engine

    asyncio.run(test_engine.dispose())
    command.downgrade(alembic_config, "base")


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    with KafkaContainer().with_kraft() as kafka:
        yield kafka.get_bootstrap_server()


@pytest.fixture
def issue(monkeypatch: pytest.MonkeyPatch) -> Callable[..., str]:
    """Issues bearer tokens the public API accepts: `issue(user_id)` for
    a customer, `issue(user_id, ["ADMIN"])` for staff. Signed by a key
    made for this test, served through a fake JWKS endpoint."""
    private_key = Ed25519PrivateKey.generate()
    pem = private_key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    x = base64.urlsafe_b64encode(public).rstrip(b"=").decode("ascii")
    jwks_app = FastAPI()

    @jwks_app.get("/.well-known/jwks.json")
    async def _jwks() -> dict:
        return {"keys": [{"kty": "OKP", "crv": "Ed25519", "x": x, "kid": "k", "alg": "EdDSA"}]}

    monkeypatch.setattr(
        auth_module,
        "jwt_verifier",
        JWTVerifier(
            jwks_url="http://identity/.well-known/jwks.json",
            issuer=settings.jwt_issuer,
            transport=httpx.ASGITransport(app=jwks_app),
        ),
    )

    def _issue(user_id: uuid.UUID, roles: list[str] | None = None) -> str:
        now = datetime.now(UTC)
        claims = {
            "sub": str(user_id),
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "roles": roles or ["USER"],
        }
        return jwt.encode(claims, pem, algorithm="EdDSA", headers={"kid": "k"})

    return _issue

