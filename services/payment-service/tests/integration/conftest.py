import asyncio
import base64
from datetime import UTC, datetime, timedelta
from uuid import UUID

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


@pytest.fixture(scope="module")
def kafka_bootstrap_servers() -> str:
    # Single-node KRaft mode — no separate Zookeeper container needed,
    # same setup used in docker-compose.yml for local dev.
    with KafkaContainer().with_kraft() as kafka:
        yield kafka.get_bootstrap_server()


@pytest.fixture
def migrated_database(postgres_url: str, monkeypatch: pytest.MonkeyPatch):
    """Runs Alembic migrations against a fresh schema in the module's
    PostgreSQL testcontainer, then points the app's DB session machinery
    at it, so repositories/services/API calls under test hit a real,
    migrated database instead of the process's configured one.
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


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


@pytest.fixture
def issue_access_token(monkeypatch: pytest.MonkeyPatch):
    """Wires app.core.auth.jwt_verifier to a fake, in-process JWKS
    endpoint (no real network call) signed with a fresh test-only
    Ed25519 key, and returns a function that mints a valid access token
    for a given user id — the same shape identity-service would issue.
    """
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    raw_public = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw
    )
    kid = "test-key"
    jwks = {
        "keys": [
            {
                "kty": "OKP",
                "crv": "Ed25519",
                "x": _b64url(raw_public),
                "kid": kid,
                "use": "sig",
                "alg": "EdDSA",
            }
        ]
    }

    jwks_app = FastAPI()

    @jwks_app.get("/.well-known/jwks.json")
    async def _jwks() -> dict:
        return jwks

    verifier = JWTVerifier(
        jwks_url="http://identity/.well-known/jwks.json",
        issuer=settings.jwt_issuer,
        transport=httpx.ASGITransport(app=jwks_app),
    )
    monkeypatch.setattr(auth_module, "jwt_verifier", verifier)

    def _issue(user_id: UUID, roles: list[str] | None = None) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": str(user_id),
            "iss": settings.jwt_issuer,
            "iat": now,
            "exp": now + timedelta(minutes=15),
            "roles": roles or ["USER"],
        }
        return jwt.encode(payload, private_pem, algorithm="EdDSA", headers={"kid": kid})

    return _issue
