import pytest
from fincore_common.kafka import EventProducer
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine

from app.core import kafka as kafka_module
from app.db import session as db_session
from app.main import app

# `postgres_url`, `kafka_bootstrap_servers` (module-scoped) come from
# tests/integration/conftest.py.


@pytest.fixture
async def real_database(postgres_url: str, monkeypatch: pytest.MonkeyPatch):
    test_engine = create_async_engine(postgres_url, pool_pre_ping=True)
    monkeypatch.setattr(db_session, "engine", test_engine)
    yield test_engine
    await test_engine.dispose()


@pytest.fixture
async def real_kafka(kafka_bootstrap_servers: str, monkeypatch: pytest.MonkeyPatch):
    producer = EventProducer(kafka_bootstrap_servers)
    await producer.start()
    monkeypatch.setattr(kafka_module, "side_channel_producer", producer)
    yield producer
    await producer.stop()


async def test_ready_returns_ok_when_database_and_kafka_are_reachable(
    real_database, real_kafka
) -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_fails_when_database_is_unreachable(
    real_kafka, monkeypatch: pytest.MonkeyPatch
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


async def test_ready_fails_when_kafka_is_unreachable(real_database) -> None:
    # kafka_module.side_channel_producer is the module's real, unstarted
    # singleton here (no `real_kafka` fixture) — check_connection()
    # raises RuntimeError because start() was never called, the same
    # observable failure a genuinely unreachable broker would produce.
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/ready")

    assert response.status_code == 503
