import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from testcontainers.community.kafka import KafkaContainer
from testcontainers.community.postgres import PostgresContainer

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
