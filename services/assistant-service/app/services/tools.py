"""The assistant's tools: read-only views of the signed-in customer's own
data, fetched from the same public APIs the web app uses, with the
customer's own bearer token. Each service authorizes the call exactly as
it would for the web app, so a tool can never return another customer's
data, and nothing here can move money or change anything.

Amounts are rendered here ("1,234.56 UZS") and the raw minor-unit
integers are dropped, so the model quotes figures instead of doing
arithmetic on them.
"""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import httpx
from fincore_common import async_client, minor_to_decimal, minor_unit_exponent

from app.core.config import settings

# Tests swap in an httpx.MockTransport.
transport: httpx.AsyncBaseTransport | None = None

_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
_PAGE = 25


def _schema(**properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties),
        "additionalProperties": False,
    }


_ID = {"type": "string", "description": "A UUID, exactly as returned by another tool."}

TOOLS: list[dict[str, Any]] = [
    {
        "name": "get_my_profile",
        "description": "The signed-in customer's profile: name, email, phone, account "
        "status (ACTIVE, SUSPENDED, BLOCKED) and when the account was created.",
        "input_schema": _schema(),
        "strict": True,
    },
    {
        "name": "list_my_wallets",
        "description": "Every wallet the customer owns, with its id, currency, status and "
        "balances: available (spendable now), on_hold (reserved by payments in progress) "
        "and ledger balance.",
        "input_schema": _schema(),
        "strict": True,
    },
    {
        "name": "get_wallet_entries",
        "description": f"The {_PAGE} most recent ledger entries of one of the customer's "
        "wallets: money in (CREDIT) and out (DEBIT), newest first. Use for questions about "
        "money received, or a wallet's balance history.",
        "input_schema": _schema(wallet_id=_ID),
        "strict": True,
    },
    {
        "name": "list_my_transactions",
        "description": f"The {_PAGE} most recent transfers and payments the customer "
        "started, newest first, with reference, type, status, amount and dates.",
        "input_schema": _schema(),
        "strict": True,
    },
    {
        "name": "get_transaction_details",
        "description": "Full details of one transfer or payment the customer started: "
        "status, failure reason, fraud decision, source wallet, destination wallet or "
        "merchant, refunded amount. Use to explain why something failed or is pending.",
        "input_schema": _schema(transaction_id=_ID),
        "strict": True,
    },
    {
        "name": "list_my_merchants",
        "description": "Merchants the customer owns, with id, name and status.",
        "input_schema": _schema(),
        "strict": True,
    },
    {
        "name": "list_merchant_payments",
        "description": f"The {_PAGE} most recent payments received by one of the "
        "customer's merchants, with status and refunded amount.",
        "input_schema": _schema(merchant_id=_ID),
        "strict": True,
    },
    {
        "name": "list_my_sessions",
        "description": "Devices currently signed in to the customer's account: device, IP "
        "address, sign-in time, last activity, and which one is this device.",
        "input_schema": _schema(),
        "strict": True,
    },
    {
        "name": "get_current_time",
        "description": "The current date and time (UTC). Use before saying how long ago "
        "something happened.",
        "input_schema": _schema(),
        "strict": True,
    },
]


@dataclass(frozen=True)
class ToolOutcome:
    content: str
    is_error: bool = False


class _Upstream:
    def __init__(self, bearer_token: str) -> None:
        self._headers = {"Authorization": f"Bearer {bearer_token}"}

    async def get(self, base_url: str, path: str, **params: Any) -> Any:
        async with async_client(
            base_url=base_url,
            timeout=settings.upstream_timeout_seconds,
            transport=transport,
        ) as client:
            response = await client.get(path, headers=self._headers, params=params or None)
        if response.status_code == 404:
            raise _NotFound()
        response.raise_for_status()
        return response.json()


class _NotFound(Exception):
    pass


def _money(amount_minor: int, currency: str) -> str:
    exponent = minor_unit_exponent(currency)
    return f"{minor_to_decimal(amount_minor, currency):,.{exponent}f} {currency}"


def _present(value: Any) -> Any:
    """Recursively replaces every `<name>_minor` integer next to a
    `currency` with a formatted `<name>` string."""
    if isinstance(value, list):
        return [_present(item) for item in value]
    if not isinstance(value, dict):
        return value
    currency = value.get("currency")
    shown: dict[str, Any] = {}
    for key, item in value.items():
        if key.endswith("_minor") and isinstance(item, int) and isinstance(currency, str):
            shown[key.removesuffix("_minor")] = _money(item, currency)
        else:
            shown[key] = _present(item)
    return shown


def _wallet(wallet: dict[str, Any]) -> dict[str, Any]:
    currency = wallet["currency"]
    return {
        "id": wallet["id"],
        "currency": currency,
        "status": wallet["status"],
        "available": _money(wallet["balance_minor"] - wallet["held_minor"], currency),
        "on_hold": _money(wallet["held_minor"], currency),
        "ledger_balance": _money(wallet["balance_minor"], currency),
        "created_at": wallet["created_at"],
    }


def _require_uuid(arguments: dict[str, Any], key: str) -> str:
    value = arguments.get(key)
    if not isinstance(value, str) or not _UUID.match(value):
        raise ValueError(f"{key} must be a UUID")
    return value


async def run_tool(name: str, arguments: dict[str, Any], *, bearer_token: str) -> ToolOutcome:
    """Runs one tool call. Never raises for expected failures: the model
    gets an error result it can explain to the customer instead."""
    api = _Upstream(bearer_token)
    identity = settings.identity_service_base_url
    ledger = settings.ledger_service_base_url
    payment = settings.payment_service_base_url
    try:
        result: Any
        if name == "get_my_profile":
            me = await api.get(identity, "/api/v1/users/me")
            fields = ("first_name", "last_name", "email", "phone", "status", "created_at")
            result = {key: me[key] for key in fields}
        elif name == "list_my_wallets":
            result = [_wallet(w) for w in await api.get(ledger, "/api/v1/wallets")]
        elif name == "get_wallet_entries":
            wallet_id = _require_uuid(arguments, "wallet_id")
            entries = await api.get(
                ledger, f"/api/v1/wallets/{wallet_id}/entries", limit=_PAGE, offset=0
            )
            result = _present(entries)
        elif name == "list_my_transactions":
            result = _present(
                await api.get(payment, "/api/v1/transactions", limit=_PAGE, offset=0)
            )
        elif name == "get_transaction_details":
            transaction_id = _require_uuid(arguments, "transaction_id")
            summary = await api.get(payment, f"/api/v1/transactions/{transaction_id}")
            kind = "transfers" if summary["type"] == "TRANSFER" else "payments"
            detail = await api.get(payment, f"/api/v1/{kind}/{transaction_id}")
            result = _present({"type": summary["type"], **detail})
        elif name == "list_my_merchants":
            result = await api.get(payment, "/api/v1/merchants")
        elif name == "list_merchant_payments":
            merchant_id = _require_uuid(arguments, "merchant_id")
            result = _present(
                await api.get(
                    payment, f"/api/v1/merchants/{merchant_id}/payments", limit=_PAGE, offset=0
                )
            )
        elif name == "list_my_sessions":
            result = await api.get(identity, "/api/v1/users/me/sessions")
        elif name == "get_current_time":
            result = {"utc": datetime.now(UTC).isoformat(timespec="seconds")}
        else:
            return ToolOutcome(f"Unknown tool {name!r}.", is_error=True)
    except ValueError as exc:
        return ToolOutcome(str(exc), is_error=True)
    except _NotFound:
        return ToolOutcome(
            "Not found: it doesn't exist or doesn't belong to this customer.", is_error=True
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            return ToolOutcome("The customer's session has expired.", is_error=True)
        return ToolOutcome("FinCore couldn't return this data right now.", is_error=True)
    except httpx.HTTPError:
        return ToolOutcome("FinCore couldn't return this data right now.", is_error=True)
    return ToolOutcome(json.dumps(result, ensure_ascii=False, sort_keys=True))
