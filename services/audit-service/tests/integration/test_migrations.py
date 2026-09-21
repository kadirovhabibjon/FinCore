import asyncio
from urllib.parse import urlsplit, urlunsplit

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, text
from sqlalchemy.exc import DBAPIError
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
    assert {"audit_logs", "dead_letters"} <= tables


def test_downgrade_then_upgrade_is_repeatable(alembic_config: Config, postgres_url: str) -> None:
    command.upgrade(alembic_config, "head")
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")

    assert "audit_logs" in _table_names(postgres_url)


def _replace_credentials(url: str, *, user: str, password: str, database: str) -> str:
    parts = urlsplit(url)
    netloc = f"{user}:{password}@{parts.hostname}:{parts.port}"
    return urlunsplit((parts.scheme, netloc, f"/{database}", "", ""))


def test_audit_logs_is_append_only(postgres_url: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """spec Section 18: "Audit storage is append-only (no UPDATE/DELETE
    permissions for the service's DB user)." Verified against a real,
    genuinely non-superuser PostgreSQL role — the testcontainer's own
    bootstrap role (used by every other test here) is a superuser, which
    bypasses privilege checks entirely and would make this test pass
    even if the migration's REVOKE did nothing. This creates a second
    role and database the same way docker-compose's init script creates
    `audit`/`audit_db` (`CREATE USER ...; CREATE DATABASE ... OWNER ...`)
    and runs the real migration as *that* role, so the REVOKE actually
    has something to bite.
    """

    async def _create_restricted_role_and_database() -> None:
        bootstrap_engine = create_async_engine(postgres_url, isolation_level="AUTOCOMMIT")
        try:
            async with bootstrap_engine.connect() as connection:
                await connection.execute(
                    text("CREATE USER audit_appendonly_test WITH PASSWORD 'test'")
                )
                await connection.execute(
                    text(
                        "CREATE DATABASE audit_appendonly_test_db "
                        "OWNER audit_appendonly_test"
                    )
                )
        finally:
            await bootstrap_engine.dispose()

    async def _check_privileges(restricted_url: str) -> None:
        engine = create_async_engine(restricted_url)
        try:
            async with engine.begin() as connection:
                await connection.execute(
                    text(
                        "INSERT INTO audit_logs "
                        "(id, event_id, action, resource_type, resource_id, result, "
                        "details, occurred_at) "
                        "VALUES (gen_random_uuid(), gen_random_uuid(), 'TEST_ACTION', "
                        "'Test', 'r-1', 'SUCCESS', '{}'::jsonb, now())"
                    )
                )

            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.begin() as connection:
                    await connection.execute(text("UPDATE audit_logs SET result = 'TAMPERED'"))

            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.begin() as connection:
                    await connection.execute(text("DELETE FROM audit_logs"))

            with pytest.raises(DBAPIError, match="permission denied"):
                async with engine.begin() as connection:
                    await connection.execute(text("TRUNCATE audit_logs"))
        finally:
            await engine.dispose()

    # Three separate top-level event loops, not nested: `command.upgrade`
    # (in between) drives its own `asyncio.run()` internally via
    # migrations/env.py, which can't be called from inside another
    # already-running loop.
    asyncio.run(_create_restricted_role_and_database())

    restricted_url = _replace_credentials(
        postgres_url,
        user="audit_appendonly_test",
        password="test",
        database="audit_appendonly_test_db",
    )
    monkeypatch.setattr(settings, "database_url", restricted_url)
    command.upgrade(Config("alembic.ini"), "head")

    asyncio.run(_check_privileges(restricted_url))
