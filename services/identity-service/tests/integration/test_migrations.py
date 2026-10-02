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
    # migrations/env.py reads settings.database_url at the moment each
    # Alembic command re-execs it, so patching the already-imported
    # settings singleton is enough to point migrations at this real
    # testcontainer instead of the process's configured database.
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


def test_upgrade_from_empty_database_creates_users_table(
    alembic_config: Config, postgres_url: str
) -> None:
    command.upgrade(alembic_config, "head")

    assert "users" in _table_names(postgres_url)


def test_downgrade_then_upgrade_is_repeatable(alembic_config: Config, postgres_url: str) -> None:
    """Regression test: an earlier version of the `create_users_table`
    migration's downgrade() dropped the `users` table but left the
    PostgreSQL native enum type (`user_status`) behind, so a second
    upgrade failed with 'type "user_status" already exists'.
    """
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    assert "users" in _table_names(postgres_url)


def test_phone_normalization_migration_rewrites_only_what_it_safely_can(
    alembic_config: Config, postgres_url: str
) -> None:
    # Start from the revision just before the data migration, whatever
    # state an earlier test left the shared database in.
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "d3f9a2c8e1b4")

    async def run(statements: list[str]) -> list:
        engine = create_async_engine(postgres_url)
        try:
            async with engine.begin() as connection:
                result = None
                for statement in statements:
                    result = await connection.execute(text(statement))
                return list(result.fetchall()) if result is not None and result.returns_rows else []
        finally:
            await engine.dispose()

    def insert(email: str, phone: str) -> str:
        return (
            "INSERT INTO users (id, email, phone, password_hash, first_name, last_name, status) "
            f"VALUES (gen_random_uuid(), '{email}', '{phone}', 'x', 'A', 'B', 'ACTIVE')"
        )

    asyncio.run(
        run(
            [
                insert("local@x.io", "917807722"),
                insert("spaced@x.io", "+998 90 111 22 33"),
                insert("broken@x.io", "+99890183042"),
                insert("taken@x.io", "+998905556677"),
                insert("clash@x.io", "905556677"),
            ]
        )
    )
    try:
        command.upgrade(alembic_config, "head")
        phones = dict(asyncio.run(run(["SELECT email, phone FROM users"])))
    finally:
        command.downgrade(alembic_config, "base")

    assert phones["local@x.io"] == "+998917807722"
    assert phones["spaced@x.io"] == "+998901112233"
    assert phones["broken@x.io"] == "+99890183042"  # can't be normalized: left as is
    assert phones["taken@x.io"] == "+998905556677"
    assert phones["clash@x.io"] == "905556677"  # its canonical form is someone else's
