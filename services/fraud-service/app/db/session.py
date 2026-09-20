from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings

engine = create_async_engine(settings.database_url, pool_pre_ping=True)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_factory() as session:
        yield session


async def check_database_connection() -> None:
    """Used by the /ready endpoint. Reads `engine` from this module's
    namespace at call time, so tests can swap it via
    `monkeypatch.setattr(session, "engine", ...)`.
    """
    async with engine.connect() as connection:
        await connection.execute(text("SELECT 1"))
