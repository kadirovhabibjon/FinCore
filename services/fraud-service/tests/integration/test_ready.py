import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.db import session as db_session
from app.main import app

# `postgres_url` (module-scoped) comes from tests/integration/conftest.py.


@pytest.fixture
async def real_database(postgres_url: str, monkeypatch: pytest.MonkeyPatch):
    test_engine = create_async_engine(postgres_url, pool_pre_ping=True)
    monkeypatch.setattr(db_session, "engine", test_engine)
    yield test_engine
    await test_engine.dispose()


async def test_ready_returns_ok_when_database_is_reachable(real_database) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_fails_when_database_is_unreachable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unreachable_engine = create_async_engine(
        "postgresql+asyncpg://user:pass@localhost:59999/nope",
        pool_pre_ping=True,
    )
    monkeypatch.setattr(db_session, "engine", unreachable_engine)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
    await unreachable_engine.dispose()
