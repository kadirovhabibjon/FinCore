from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_ready_reports_whether_the_assistant_is_configured() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).json() == {
            "status": "ok",
            "assistant": "not configured",
        }
