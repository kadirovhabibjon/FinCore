from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_health_returns_ok_without_touching_the_database() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_health_echoes_correlation_id_header() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/health", headers={"X-Correlation-ID": "test-corr-id"}
        )

    assert response.headers["X-Correlation-ID"] == "test-corr-id"
