from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import update

from app.core.config import settings
from app.db import session as db_session
from app.domain.session import RefreshToken, Session
from app.main import app

pytestmark = pytest.mark.usefixtures("migrated_database")

_USER = {
    "email": "dijkstra@example.com",
    "phone": "+998901230011",
    "password": "shortest-path-1956",
    "first_name": "Edsger",
    "last_name": "Dijkstra",
}


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _login(client: AsyncClient) -> dict:
    await client.post("/api/v1/auth/register", json=_USER)
    response = await client.post(
        "/api/v1/auth/login", json={"email": _USER["email"], "password": _USER["password"]}
    )
    return response.json()


async def _age_session(*, idle: timedelta = timedelta(0), age: timedelta = timedelta(0)) -> None:
    """Moves the (only) session's timestamps into the past, and gives its
    tokens a far-future expiry - as if issued under the old 30-day TTL -
    so only the session-level limits can end it."""
    now = datetime.now(UTC)
    async with db_session.async_session_factory() as session:
        await session.execute(
            update(Session).values(last_used_at=now - idle, created_at=now - max(age, idle))
        )
        await session.execute(update(RefreshToken).values(expires_at=now + timedelta(days=30)))
        await session.commit()


async def test_a_refresh_token_only_lasts_the_idle_window() -> None:
    async with _client() as client:
        tokens = await _login(client)

    async with db_session.async_session_factory() as session:
        expires_at = (await session.execute(RefreshToken.__table__.select())).first().expires_at
    remaining = (expires_at - datetime.now(UTC)).total_seconds()

    assert tokens["refresh_token"]
    assert 0 < remaining <= settings.refresh_token_ttl_seconds
    assert settings.refresh_token_ttl_seconds == 30 * 60
    # An active client refreshes when its access token runs out, so the
    # idle window has to be longer than that.
    assert settings.refresh_token_ttl_seconds > settings.jwt_access_token_ttl_seconds


async def test_an_idle_session_must_sign_in_again() -> None:
    async with _client() as client:
        tokens = await _login(client)
        await _age_session(idle=timedelta(minutes=31))

        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )
        # ...and it is revoked, not merely refused once.
        await _age_session(idle=timedelta(0))
        again = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert refresh.status_code == 401
    assert again.status_code == 401


async def test_an_active_session_keeps_going() -> None:
    async with _client() as client:
        tokens = await _login(client)
        await _age_session(idle=timedelta(minutes=20))

        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert refresh.status_code == 200


async def test_even_an_active_session_ends_after_the_maximum_lifetime() -> None:
    async with _client() as client:
        tokens = await _login(client)
        await _age_session(idle=timedelta(minutes=1), age=timedelta(hours=13))

        refresh = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]}
        )

    assert refresh.status_code == 401
