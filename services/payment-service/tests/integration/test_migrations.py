import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings

# `postgres_url` (module-scoped) comes from tests/integration/conftest.py.


@pytest.fixture
def alembic_config(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> Config:
    monkeypatch.setattr(settings, "database_url", postgres_url)
    return Config("alembic.ini")


def _table_names(url: str) -> set[str]:
    async def _inspect() -> set[str]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                return await connection.run_sync(
                    lambda sync_conn: set(inspect(sync_conn).get_table_names())
                )
        finally:
            await engine.dispose()

    return asyncio.run(_inspect())


def test_upgrade_from_empty_database_creates_tables(
    alembic_config: Config, postgres_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    tables = _table_names(postgres_url)
    assert "idempotency_keys" in tables
    assert "transfers" in tables


def test_downgrade_then_upgrade_is_repeatable(
    alembic_config: Config, postgres_url: str
) -> None:
    """Same lesson as identity-service and ledger-service: this
    migration's downgrade() explicitly drops the three native enum types
    it creates, so a second upgrade doesn't fail with 'type already
    exists.'
    """
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    assert "transfers" in _table_names(postgres_url)
