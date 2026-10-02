import json

import httpx
import pytest

from app.services import tools
from tests.fakes import fincore_api

WALLET_ID = "11111111-1111-4111-8111-111111111111"
TOKEN = "customer-token"


@pytest.fixture
def seen() -> list[httpx.Request]:
    return []


def _wire(monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request], routes: dict) -> None:
    def recording(handler):
        def wrapped(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        return wrapped

    monkeypatch.setattr(
        tools, "transport", fincore_api({k: recording(v) for k, v in routes.items()})
    )


async def test_wallets_are_shown_with_exact_formatted_amounts(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]
) -> None:
    _wire(
        monkeypatch,
        seen,
        {
            "GET /api/v1/wallets": lambda r: httpx.Response(
                200,
                json=[
                    {
                        "id": WALLET_ID,
                        "currency": "UZS",
                        "status": "ACTIVE",
                        "created_at": "2026-09-01T00:00:00Z",
                        "balance_minor": 123_456_789,
                        "held_minor": 5_000_000,
                    }
                ],
            )
        },
    )

    outcome = await tools.run_tool("list_my_wallets", {}, bearer_token=TOKEN)

    assert not outcome.is_error
    [wallet] = json.loads(outcome.content)
    assert wallet["available"] == "1,184,567.89 UZS"
    assert wallet["on_hold"] == "50,000.00 UZS"
    assert wallet["ledger_balance"] == "1,234,567.89 UZS"
    assert "balance_minor" not in outcome.content
    # The customer's own token goes upstream: services authorize as usual.
    assert seen[0].headers["Authorization"] == f"Bearer {TOKEN}"


async def test_transaction_details_combine_summary_and_detail(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]
) -> None:
    tid = "22222222-2222-4222-8222-222222222222"
    _wire(
        monkeypatch,
        seen,
        {
            f"GET /api/v1/transactions/{tid}": lambda r: httpx.Response(
                200, json={"id": tid, "type": "TRANSFER"}
            ),
            f"GET /api/v1/transfers/{tid}": lambda r: httpx.Response(
                200,
                json={
                    "id": tid,
                    "status": "FAILED",
                    "failure_reason": "Insufficient Funds",
                    "amount_minor": 1050,
                    "currency": "USD",
                },
            ),
        },
    )

    outcome = await tools.run_tool(
        "get_transaction_details", {"transaction_id": tid}, bearer_token=TOKEN
    )

    detail = json.loads(outcome.content)
    assert detail == {
        "type": "TRANSFER",
        "id": tid,
        "status": "FAILED",
        "failure_reason": "Insufficient Funds",
        "amount": "10.50 USD",
        "currency": "USD",
    }


async def test_ids_are_validated_before_any_request(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request]
) -> None:
    _wire(monkeypatch, seen, {})

    outcome = await tools.run_tool(
        "get_wallet_entries", {"wallet_id": "../../admin/users"}, bearer_token=TOKEN
    )

    assert outcome.is_error
    assert "UUID" in outcome.content
    assert seen == []


@pytest.mark.parametrize(
    ("status", "message"),
    [(404, "doesn't belong to this customer"), (401, "session has expired"), (503, "right now")],
)
async def test_upstream_failures_become_explainable_errors(
    monkeypatch: pytest.MonkeyPatch, seen: list[httpx.Request], status: int, message: str
) -> None:
    _wire(monkeypatch, seen, {"GET /api/v1/merchants": lambda r: httpx.Response(status, json={})})

    outcome = await tools.run_tool("list_my_merchants", {}, bearer_token=TOKEN)

    assert outcome.is_error
    assert message in outcome.content


async def test_unknown_tools_are_refused() -> None:
    outcome = await tools.run_tool("send_money", {}, bearer_token=TOKEN)
    assert outcome.is_error


def test_every_tool_is_strict_and_read_only() -> None:
    names = {tool["name"] for tool in tools.TOOLS}
    assert names == {
        "get_my_profile",
        "list_my_wallets",
        "get_wallet_entries",
        "list_my_transactions",
        "get_transaction_details",
        "list_my_merchants",
        "list_merchant_payments",
        "list_my_sessions",
        "get_current_time",
    }
    for tool in tools.TOOLS:
        assert tool["strict"] is True
        assert tool["input_schema"]["additionalProperties"] is False
        assert set(tool["input_schema"]["required"]) == set(tool["input_schema"]["properties"])
