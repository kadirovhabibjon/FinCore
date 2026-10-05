"""The OpenAI-compatible provider (Gemini, Groq, ...), against a scripted
Chat Completions API."""

import json
import uuid
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.v1 import chat as chat_module
from app.core.config import settings
from app.main import app
from app.services import compatible, tools
from app.services.rate_limit import SlidingWindowLimiter
from tests.fakes import fincore_api, install_token_issuer

WALLET = {
    "id": "11111111-1111-4111-8111-111111111111",
    "currency": "UZS",
    "status": "ACTIVE",
    "created_at": "2026-09-01T00:00:00Z",
    "balance_minor": 150_000,
    "held_minor": 0,
}


def completion(message: dict[str, Any], finish_reason: str = "stop") -> dict[str, Any]:
    return {"choices": [{"index": 0, "message": message, "finish_reason": finish_reason}]}


def says(content: str) -> dict[str, Any]:
    return completion({"role": "assistant", "content": content})


def calls(call_id: str, name: str, arguments: str = "{}") -> dict[str, Any]:
    call = {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}
    return completion(
        {"role": "assistant", "content": None, "tool_calls": [call]}, finish_reason="tool_calls"
    )


class FakeModelApi:
    def __init__(self, *responses: dict[str, Any] | tuple[int, dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.requests: list[httpx.Request] = []
        self.bodies: list[dict[str, Any]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        self.bodies.append(json.loads(request.content))
        scripted = self._responses.pop(0)
        status, body = scripted if isinstance(scripted, tuple) else (200, scripted)
        return httpx.Response(status, json=body)


@pytest.fixture
def issue(monkeypatch: pytest.MonkeyPatch) -> Callable[[uuid.UUID], str]:
    monkeypatch.setattr(chat_module, "limiter", SlidingWindowLimiter(30, 3600))
    monkeypatch.setattr(settings, "assistant_provider", "openai_compatible")
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_base_url", "https://llm.test/v1/")
    monkeypatch.setattr(settings, "llm_model", "test-model")
    monkeypatch.setattr(settings, "llm_fallback_models", "")
    return install_token_issuer(monkeypatch)


def _use(monkeypatch: pytest.MonkeyPatch, api: FakeModelApi) -> None:
    monkeypatch.setattr(compatible, "transport", httpx.MockTransport(api))


async def _chat(token: str, content: str) -> httpx.Response:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/api/v1/assistant/chat",
            json={"messages": [{"role": "user", "content": content}]},
            headers={"Authorization": f"Bearer {token}"},
        )


async def test_answers_from_the_customers_data_through_a_tool(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    upstream: list[httpx.Request] = []

    def wallets(request: httpx.Request) -> httpx.Response:
        upstream.append(request)
        return httpx.Response(200, json=[WALLET])

    monkeypatch.setattr(tools, "transport", fincore_api({"GET /api/v1/wallets": wallets}))
    api = FakeModelApi(calls("call_1", "list_my_wallets"), says(" Sizda 1,500.00 UZS bor. "))
    _use(monkeypatch, api)
    token = issue(uuid.uuid4())

    response = await _chat(token, "Balansim qancha?")

    assert response.status_code == 200
    assert response.json() == {"reply": "Sizda 1,500.00 UZS bor."}
    # The tool read the customer's data with the customer's own token;
    # the model API got the service's key, never that token.
    assert upstream[0].headers["Authorization"] == f"Bearer {token}"
    assert str(api.requests[0].url) == "https://llm.test/v1/chat/completions"
    assert api.requests[0].headers["Authorization"] == "Bearer test-key"
    assert token not in api.requests[0].content.decode()

    first, second = api.bodies
    assert first["model"] == "test-model"
    assert first["messages"][0]["role"] == "system"
    assert "<knowledge_base>" in first["messages"][0]["content"]
    assert first["messages"][1] == {"role": "user", "content": "Balansim qancha?"}
    functions = {t["function"]["name"]: t["function"] for t in first["tools"]}
    assert set(functions) == {t["name"] for t in tools.TOOLS}
    # Portable schemas: nothing for a tool without arguments, and no
    # Claude-only keywords on the others.
    assert "parameters" not in functions["list_my_wallets"]
    assert set(functions["get_wallet_entries"]["parameters"]) == {"type", "properties", "required"}
    # Second round: the model's tool call replayed, then the result.
    assert second["messages"][2]["tool_calls"][0]["id"] == "call_1"
    result = second["messages"][3]
    assert result["role"] == "tool" and result["tool_call_id"] == "call_1"
    assert json.loads(result["content"])[0]["available"] == "1,500.00 UZS"


async def test_unparseable_tool_arguments_go_back_to_the_model_as_an_error(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    api = FakeModelApi(calls("c1", "get_wallet_entries", "{not json"), says("Qaysi hamyon?"))
    _use(monkeypatch, api)

    response = await _chat(issue(uuid.uuid4()), "tarix")

    assert response.json() == {"reply": "Qaysi hamyon?"}
    assert "not a JSON object" in api.bodies[1]["messages"][3]["content"]


async def test_tool_rounds_are_capped(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    monkeypatch.setattr(settings, "assistant_max_tool_rounds", 2)
    api = FakeModelApi(*[calls(f"c{i}", "get_current_time") for i in range(2)])
    _use(monkeypatch, api)

    response = await _chat(issue(uuid.uuid4()), "loop")

    assert "couldn't finish" in response.json()["reply"]
    assert len(api.bodies) == 2


@pytest.mark.parametrize(
    ("status", "title"),
    [
        (401, "Assistant Not Configured"),
        (429, "Assistant Unavailable"),
        (500, "Assistant Unavailable"),
    ],
)
async def test_model_api_errors_become_503(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str], status: int, title: str
) -> None:
    _use(monkeypatch, FakeModelApi((status, {"error": {"message": "x"}})))

    response = await _chat(issue(uuid.uuid4()), "hi")

    assert response.status_code == 503
    assert response.json()["title"] == title


async def test_a_filtered_reply_gets_a_polite_refusal(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    blocked = completion({"role": "assistant", "content": None}, finish_reason="content_filter")
    _use(monkeypatch, FakeModelApi(blocked))

    response = await _chat(issue(uuid.uuid4()), "...")

    assert "can't help with that" in response.json()["reply"]


async def test_without_a_key_the_chat_says_it_isnt_configured(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    monkeypatch.setattr(settings, "llm_api_key", "")

    response = await _chat(issue(uuid.uuid4()), "hi")

    assert response.status_code == 503
    assert response.json()["title"] == "Assistant Not Configured"


async def test_an_overloaded_model_falls_back_to_the_next_one(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    monkeypatch.setattr(settings, "llm_fallback_models", "retired-model, spare-model")
    api = FakeModelApi(
        (503, {"error": {"message": "high demand"}}),
        (404, {"error": {"message": "no longer available"}}),
        calls("c1", "get_current_time"),
        says("Salom!"),
    )
    _use(monkeypatch, api)

    response = await _chat(issue(uuid.uuid4()), "salom")

    assert response.json() == {"reply": "Salom!"}
    # Once a model answers, the rest of the turn stays on it.
    assert [body["model"] for body in api.bodies] == [
        "test-model",
        "retired-model",
        "spare-model",
        "spare-model",
    ]


async def test_a_rejected_key_is_not_retried_on_other_models(
    monkeypatch: pytest.MonkeyPatch, issue: Callable[[uuid.UUID], str]
) -> None:
    monkeypatch.setattr(settings, "llm_fallback_models", "spare-model")
    api = FakeModelApi((401, {"error": {"message": "bad key"}}))
    _use(monkeypatch, api)

    response = await _chat(issue(uuid.uuid4()), "hi")

    assert response.json()["title"] == "Assistant Not Configured"
    assert len(api.bodies) == 1
