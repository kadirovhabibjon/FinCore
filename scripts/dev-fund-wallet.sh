#!/usr/bin/env bash
# Credits a wallet in the local docker-compose stack, for trying the UI.
#
#   ./scripts/dev-fund-wallet.sh <wallet-id> <amount> [currency]
#   ./scripts/dev-fund-wallet.sh 3f2b8c1e-... 1000.00 UZS
#
# There is no public deposit API (spec Section 20): money enters through
# ledger-service's internal postings API, debiting the EXTERNAL_FUNDING
# clearing account (ADR-0002) — the same path tests/e2e uses. It talks to
# ledger-service's host port directly, never through the gateway, which
# doesn't route /internal/*. Local development only.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 <wallet-id> <amount> [currency]" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LEDGER_URL="${LEDGER_URL:-http://localhost:8092}"
TOKEN="$(grep -E '^INTERNAL_SERVICE_TOKEN=' "$ROOT/services/ledger-service/.env" | cut -d= -f2-)"

python3 - "$1" "$2" "${3:-UZS}" "$LEDGER_URL" "$TOKEN" <<'PY'
import json
import sys
import urllib.request
import uuid
from decimal import Decimal

wallet_id, amount, currency, base_url, token = sys.argv[1:]
exponent = {"UZS": 2, "USD": 2}[currency]
scaled = Decimal(amount) * 10**exponent
if scaled != scaled.to_integral_value() or scaled <= 0:
    sys.exit(f"invalid amount {amount!r} for {currency}")
amount_minor = int(scaled)
headers = {"X-Internal-Token": token, "Content-Type": "application/json"}


def call(method: str, path: str, body: dict | None = None) -> dict:
    request = urllib.request.Request(
        base_url + path,
        method=method,
        headers=headers,
        data=json.dumps(body).encode() if body is not None else None,
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


funding = call("GET", f"/internal/v1/accounts/system?kind=EXTERNAL_FUNDING&currency={currency}")
call(
    "POST",
    "/internal/v1/postings",
    {
        "source_service": "dev-funding",
        "source_id": f"dev-fund-{uuid.uuid4()}",
        "type": "DEPOSIT",
        "currency": currency,
        "entries": [
            {"account_id": funding["id"], "direction": "DEBIT", "amount_minor": amount_minor},
            {"account_id": wallet_id, "direction": "CREDIT", "amount_minor": amount_minor},
        ],
    },
)
print(f"credited {amount} {currency} to wallet {wallet_id}")
PY
