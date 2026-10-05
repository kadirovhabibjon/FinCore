"""The same chat turn as app/services/assistant.py, answered through an
OpenAI-compatible Chat Completions API instead of Claude - Google Gemini
and Groq both expose one and have a free tier. Same system prompt, same
read-only tools, same cap on tool rounds; only the wire format differs.

Plain httpx rather than an SDK: one endpoint, and the provider is chosen
by base URL, not by library.
"""

import asyncio
import json
import logging
from typing import Any

import httpx

from app.core.config import settings
from app.core.exceptions import AssistantNotConfiguredError, AssistantUnavailableError
from app.services.assistant import REFUSAL_REPLY, SYSTEM_PROMPT, TOO_LONG_REPLY, ChatTurn
from app.services.tools import TOOLS, ToolOutcome, run_tool

logger = logging.getLogger(__name__)

# Tests swap in an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None


def _function(tool: dict[str, Any]) -> dict[str, Any]:
    """A Claude tool definition as a Chat Completions function. Kept to
    what every provider accepts: no `strict`, no `additionalProperties`,
    and no parameters object at all for a tool that takes none (Gemini
    rejects an object schema without properties)."""
    function: dict[str, Any] = {"name": tool["name"], "description": tool["description"]}
    schema = tool["input_schema"]
    if schema["properties"]:
        function["parameters"] = {
            "type": "object",
            "properties": schema["properties"],
            "required": schema["required"],
        }
    return {"type": "function", "function": function}


_FUNCTIONS = [_function(tool) for tool in TOOLS]


async def _run(call: dict[str, Any], *, bearer_token: str) -> ToolOutcome:
    function = call.get("function") or {}
    try:
        arguments = json.loads(function.get("arguments") or "{}")
    except ValueError:
        arguments = None
    if not isinstance(arguments, dict):
        return ToolOutcome(content="The arguments were not a JSON object.", is_error=True)
    return await run_tool(str(function.get("name")), arguments, bearer_token=bearer_token)


def _models() -> list[str]:
    fallbacks = (name.strip() for name in settings.llm_fallback_models.split(","))
    return [settings.llm_model, *(name for name in fallbacks if name)]


async def _complete(
    client: httpx.AsyncClient, messages: list[dict[str, Any]], models: list[str]
) -> tuple[dict[str, Any], str]:
    """The next reply, from the first of `models` that gives one, and
    which model that was. A model that is overloaded, over its quota,
    retired or erroring is skipped; a rejected key fails at once."""
    busy = False
    for model in models:
        try:
            response = await client.post(
                "/chat/completions",
                json={
                    "model": model,
                    "messages": messages,
                    "tools": _FUNCTIONS,
                    "max_tokens": settings.llm_max_tokens,
                },
            )
        except httpx.HTTPError as exc:
            logger.warning("Model API unreachable for %s: %s", model, type(exc).__name__)
            busy = True
            continue

        if response.status_code in (401, 403):
            logger.error("The model API rejected the configured key (%s)", response.status_code)
            raise AssistantNotConfiguredError("The assistant's API key was rejected.")
        if response.status_code != 200:
            # The API's own message, which never contains the key.
            logger.warning(
                "Model API error %s for %s: %s", response.status_code, model, response.text[:300]
            )
            busy = busy or response.status_code in (429, 503)
            continue
        try:
            choice = response.json()["choices"][0]
            if not isinstance(choice.get("message"), dict):
                raise TypeError("no message")
        except (ValueError, LookupError, TypeError, AttributeError):
            logger.warning("Model API answered 200 with an unexpected body for %s", model)
            continue
        return dict(choice), model

    logger.error("No model could answer (tried %s)", ", ".join(models))
    if busy:
        raise AssistantUnavailableError("The assistant is busy. Try again shortly.")
    raise AssistantUnavailableError("The assistant is unavailable right now.")


async def answer(history: list[ChatTurn], *, bearer_token: str) -> str:
    """The assistant's reply to the last (user) turn of `history`."""
    if not settings.llm_api_key:
        raise AssistantNotConfiguredError("The assistant needs an API key (LLM_API_KEY) to answer.")
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *({"role": turn.role, "content": turn.content} for turn in history),
    ]

    async with httpx.AsyncClient(
        base_url=settings.llm_base_url.rstrip("/"),
        headers={"Authorization": f"Bearer {settings.llm_api_key}"},
        timeout=settings.llm_timeout_seconds,
        transport=transport,
    ) as client:
        models = _models()
        for _ in range(settings.assistant_max_tool_rounds):
            choice, used = await _complete(client, messages, models)
            # Stay on the model that answered for the rest of the turn:
            # what it attached to its tool calls is only valid for it.
            models = models[models.index(used) :]
            message = choice["message"]
            calls = message.get("tool_calls") or []

            if choice.get("finish_reason") == "content_filter":
                return REFUSAL_REPLY
            if not calls:
                content = message.get("content")
                return (content.strip() if isinstance(content, str) else "") or TOO_LONG_REPLY

            # Appended as received: some providers attach fields to a
            # tool call that they expect back unchanged on the next round.
            messages.append({key: value for key, value in message.items() if value is not None})
            outcomes = await asyncio.gather(
                *(_run(call, bearer_token=bearer_token) for call in calls)
            )
            messages.extend(
                {"role": "tool", "tool_call_id": call.get("id"), "content": outcome.content}
                for call, outcome in zip(calls, outcomes, strict=True)
            )

    return TOO_LONG_REPLY
