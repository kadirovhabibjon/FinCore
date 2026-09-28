#!/usr/bin/env bash
# Regenerates contracts/openapi/<service>.json from each service's own
# FastAPI app (spec Section 22: "contracts/openapi — public + internal
# API specs"). Each service's `tests/unit/test_openapi_contract.py` fails
# whenever its app no longer matches the committed file, so an API change
# can't land without the contract diff showing up in review alongside it.
#
# Uses each service's own .venv, the same one its tests run in.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/contracts/openapi"
mkdir -p "$OUT"

for service_dir in "$ROOT"/services/*/; do
  service="$(basename "$service_dir")"
  (
    cd "$service_dir"
    .venv/bin/python - "$OUT/$service.json" <<'EOF'
import json
import os
import sys

# Same placeholders each service's tests/conftest.py uses: importing
# app.main loads settings, which need syntactically valid values, but
# nothing here connects to anything.
for key, value in {
    "DATABASE_URL": "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
    "INTERNAL_SERVICE_TOKEN": "placeholder",
    "IDENTITY_SERVICE_JWKS_URL": "http://placeholder/.well-known/jwks.json",
    "LEDGER_SERVICE_BASE_URL": "http://placeholder",
    "FRAUD_SERVICE_BASE_URL": "http://placeholder",
    "PAYMENT_SERVICE_BASE_URL": "http://placeholder",
}.items():
    os.environ[key] = value

from app.main import app  # noqa: E402

with open(sys.argv[1], "w") as fh:
    json.dump(app.openapi(), fh, indent=2, sort_keys=True)
    fh.write("\n")
EOF
  )
  echo "wrote  contracts/openapi/$service.json"
done
