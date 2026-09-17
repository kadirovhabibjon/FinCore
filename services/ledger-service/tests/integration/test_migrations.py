import asyncio

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
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


def _system_account_rows(url: str) -> list[tuple[str, str]]:
    async def _query() -> list[tuple[str, str]]:
        engine = create_async_engine(url)
        try:
            async with engine.connect() as connection:
                result = await connection.execute(
                    text("SELECT kind, currency FROM ledger_accounts ORDER BY kind, currency")
                )
                return [(row.kind, row.currency) for row in result]
        finally:
            await engine.dispose()

    return asyncio.run(_query())


def test_upgrade_from_empty_database_creates_ledger_accounts_table(
    alembic_config: Config, postgres_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    assert "ledger_accounts" in _table_names(postgres_url)


def test_upgrade_seeds_one_system_account_per_kind_and_currency(
    alembic_config: Config, postgres_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    rows = _system_account_rows(postgres_url)

    assert len(rows) == 10  # 5 system kinds x 2 currencies
    assert ("FEES", "UZS") in rows
    assert ("FEES", "USD") in rows
    assert ("SUSPENSE", "UZS") in rows
    assert "USER_WALLET" not in {kind for kind, _ in rows}


def test_downgrade_then_upgrade_is_repeatable(
    alembic_config: Config, postgres_url: str
) -> None:
    """Same lesson as identity-service's first migration: PostgreSQL
    native enum types aren't dropped by drop_table(), so a naive
    downgrade() would make a second upgrade fail with 'type already
    exists'. Both account_kind and account_status are cleaned up
    explicitly in this migration's downgrade().
    """
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    assert "ledger_accounts" in _table_names(postgres_url)
    assert len(_system_account_rows(postgres_url)) == 10
