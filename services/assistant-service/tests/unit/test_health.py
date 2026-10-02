from httpx import ASGITransport, AsyncClient

from app.main import app


async def test_ready_reports_whether_the_assistant_is_configured() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/health")).json() == {"status": "ok"}
        assert (await client.get("/ready")).json() == {
            "status": "ok",
            "assistant": "not configured",
        }


def test_a_workspace_id_is_sent_with_every_request(monkeypatch) -> None:
    from app.core.config import settings
    from app.services import assistant

    monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-usr-test")
    monkeypatch.setattr(settings, "anthropic_workspace_id", "wrkspc_test")

    client = assistant._client()

    assert client.default_headers["anthropic-workspace-id"] == "wrkspc_test"
