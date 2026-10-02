import json
import uuid
from collections.abc import Callable

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import chat as chat_module
from app.core.config import settings
from app.main import app
from app.services import assistant, tools
from app.services.rate_limit import SlidingWindowLimiter
from tests.fakes import FakeClaude, fincore_api, install_token_issuer, message, text, tool_use

WALLET = {
    "id": "11111111-1111-4111-8111-111111111111",
    "currency": "UZS",
    "status": "ACTIVE",
    "created_at": "2026-09-01T00:00:00Z",
    "balance_minor": 150_000,
    "held_minor": 0,
}


@pytest.fixture
def issue(monkeypatch: pytest.MonkeyPatch) -> Callable[[uuid.UUID], str]:
    monkeypatch.setattr(chat_module, "limiter", SlidingWindowLimiter(30, 3600))
    return install_token_issuer(monkeypatch)


def _use(monkeypatch: pytest.MonkeyPatch, claude: FakeClaude) -> None:
    monkeypatch.setattr(assistant, "client_factory", claude.client)


async def _chat(token: str | None, messages: list[dict]) -> httpx.Response:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/v1/assistant/chat", json={"messages": messages}, headers=headers
        )


async def test_answers_from_the_customers_data_through_a_tool(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    upstream: list[httpx.Request] = []

    def wallets(request: httpx.Request) -> httpx.Response:
        upstream.append(request)
        return httpx.Response(200, json=[WALLET])

    monkeypatch.setattr(tools, "transport", fincore_api({"GET /api/v1/wallets": wallets}))
    claude = FakeClaude(
        message(tool_use("call_1", "list_my_wallets"), stop_reason="tool_use"),
        message(text("Your UZS wallet has 1,500.00 UZS available.")),
    )
    _use(monkeypatch, claude)
    token = issue(uuid.uuid4())

    response = await _chat(token, [{"role": "user", "content": "Balansim qancha?"}])

    assert response.status_code == 200
    assert response.json() == {"reply": "Your UZS wallet has 1,500.00 UZS available."}
    assert upstream[0].headers["Authorization"] == f"Bearer {token}"

    first, second = claude.requests
    # The request the real SDK built: model, effort, thinking, fallbacks,
    # strict read-only tools, and a cached system prompt with the knowledge base.
    assert first["model"] == "claude-opus-5-5"
    assert first["output_config"] == {"effort": "medium"}
    assert first["thinking"] == {"type": "adaptive"}
    assert first["fallbacks"] == "default"
    assert first["system"][0]["cache_control"] == {"type": "ephemeral"}
    assert "<knowledge_base>" in first["system"][0]["text"]
    assert {t["name"] for t in first["tools"]} == {t["name"] for t in tools.TOOLS}
    assert first["messages"] == [{"role": "user", "content": "Balansim qancha?"}]
    # Second round: the assistant turn replayed unchanged, then the tool result.
    assert second["messages"][1]["content"][0]["name"] == "list_my_wallets"
    result = second["messages"][2]["content"][0]
    assert result["tool_use_id"] == "call_1"
    assert result["is_error"] is False
    assert json.loads(result["content"])[0]["available"] == "1,500.00 UZS"


async def test_a_refusal_gets_a_polite_reply(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    _use(monkeypatch, FakeClaude(message(stop_reason="refusal")))

    response = await _chat(issue(uuid.uuid4()), [{"role": "user", "content": "..."}])

    assert response.status_code == 200
    assert "can't help with that" in response.json()["reply"]


async def test_tool_rounds_are_capped(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    monkeypatch.setattr(settings, "assistant_max_tool_rounds", 2)
    claude = FakeClaude(
        *[message(tool_use(f"c{i}", "get_current_time"), stop_reason="tool_use") for i in range(2)]
    )
    _use(monkeypatch, claude)

    response = await _chat(issue(uuid.uuid4()), [{"role": "user", "content": "loop"}])

    assert "couldn't finish" in response.json()["reply"]
    assert len(claude.requests) == 2


async def test_claude_api_errors_become_503(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    _use(
        monkeypatch,
        FakeClaude((529, {"type": "error", "error": {"type": "overloaded_error", "message": "x"}})),
    )

    response = await _chat(issue(uuid.uuid4()), [{"role": "user", "content": "hi"}])

    assert response.status_code == 503
    assert response.json()["title"] == "Assistant Unavailable"


async def test_without_an_api_key_the_chat_says_it_isnt_configured(
    issue: Callable[[uuid.UUID], str],
) -> None:
    response = await _chat(issue(uuid.uuid4()), [{"role": "user", "content": "hi"}])

    assert response.status_code == 503
    assert response.json()["title"] == "Assistant Not Configured"


async def test_needs_a_valid_token() -> None:
    assert (await _chat(None, [{"role": "user", "content": "hi"}])).status_code == 401
    assert (await _chat("forged", [{"role": "user", "content": "hi"}])).status_code == 401


@pytest.mark.parametrize(
    "messages",
    [
        [{"role": "assistant", "content": "hi"}],
        [{"role": "user", "content": "a"}, {"role": "user", "content": "b"}],
        [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}],
        [{"role": "user", "content": "x" * 2001}],
        [{"role": "user" if i % 2 == 0 else "assistant", "content": "m"} for i in range(21)],
    ],
)
async def test_malformed_conversations_are_rejected_before_any_api_call(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str], messages: list[dict]
) -> None:
    claude = FakeClaude()
    _use(monkeypatch, claude)

    response = await _chat(issue(uuid.uuid4()), messages)

    assert response.status_code == 422
    assert claude.requests == []


async def test_each_customer_is_rate_limited(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    monkeypatch.setattr(chat_module, "limiter", SlidingWindowLimiter(1, 3600))
    _use(monkeypatch, FakeClaude(message(text("one")), message(text("other"))))
    alice, bob = issue(uuid.uuid4()), issue(uuid.uuid4())

    first = await _chat(alice, [{"role": "user", "content": "hi"}])
    second = await _chat(alice, [{"role": "user", "content": "hi"}])
    other = await _chat(bob, [{"role": "user", "content": "hi"}])

    assert first.status_code == 200
    assert second.status_code == 429
    assert other.status_code == 200
