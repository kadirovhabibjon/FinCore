#!/usr/bin/env bash
# Writes a docker-compose-ready `.env` for every service: container-
# network hostnames (not the localhost URLs in each .env.example, which
# are for running a service directly), fresh random internal tokens, and
# a freshly generated Ed25519 JWT signing key.
#
# Existing .env files are left untouched unless --force is given, so
# running this never silently replaces a developer's own configuration.
#
# Used by CI's e2e job (.github/workflows/ci.yml) and as the one-command
# local setup in the README.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FORCE=0
[[ "${1:-}" == "--force" ]] && FORCE=1

random_token() { openssl rand -hex 24; }

# Reuses the token from the first of the given services that already has
# a .env (unless --force), so filling in one missing file never leaves it
# holding a different secret than the siblings it has to talk to.
token_for() {
  if [[ "$FORCE" -eq 0 ]]; then
    local service existing
    for service in "$@"; do
      existing="$ROOT/services/$service/.env"
      if [[ -f "$existing" ]] && grep -q "^INTERNAL_SERVICE_TOKEN=" "$existing"; then
        grep "^INTERNAL_SERVICE_TOKEN=" "$existing" | head -1 | cut -d= -f2-
        return
      fi
    done
  fi
  random_token
}

# fraud/ledger/payment/webhook share one token: payment-service sends the
# same secret to ledger's and fraud's internal APIs, and webhook-service
# sends it to payment-service's. notification-service and audit-service
# each get their own — nothing else calls into them.
SHARED_TOKEN="$(token_for ledger-service payment-service fraud-service webhook-service)"
NOTIFICATION_TOKEN="$(token_for notification-service)"
AUDIT_TOKEN="$(token_for audit-service)"

write_env() {
  local service="$1"
  local target="$ROOT/services/$service/.env"
  if [[ -f "$target" && "$FORCE" -eq 0 ]]; then
    echo "skip   services/$service/.env (exists; use --force to overwrite)"
    cat >/dev/null
    return
  fi
  cat >"$target"
  echo "wrote  services/$service/.env"
}

JWT_PRIVATE_KEY="$(openssl genpkey -algorithm ed25519)"

write_env identity-service <<EOF
SERVICE_NAME=identity-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://identity:identity@postgres:5432/identity_db
JWT_ISSUER=fincore-identity-service
JWT_KEY_ID=identity-dev
JWT_ACCESS_TOKEN_TTL_SECONDS=900
JWT_PRIVATE_KEY="$JWT_PRIVATE_KEY"
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
EOF

write_env ledger-service <<EOF
SERVICE_NAME=ledger-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://ledger:ledger@postgres:5432/ledger_db
IDENTITY_SERVICE_JWKS_URL=http://identity-service:8000/.well-known/jwks.json
JWT_ISSUER=fincore-identity-service
INTERNAL_SERVICE_TOKEN=$SHARED_TOKEN
EOF

write_env fraud-service <<EOF
SERVICE_NAME=fraud-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://fraud:fraud@postgres:5432/fraud_db
INTERNAL_SERVICE_TOKEN=$SHARED_TOKEN
EOF

write_env payment-service <<EOF
SERVICE_NAME=payment-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://payment:payment@postgres:5432/payment_db
IDENTITY_SERVICE_JWKS_URL=http://identity-service:8000/.well-known/jwks.json
JWT_ISSUER=fincore-identity-service
INTERNAL_SERVICE_TOKEN=$SHARED_TOKEN
LEDGER_SERVICE_BASE_URL=http://ledger-service:8000
FRAUD_SERVICE_BASE_URL=http://fraud-service:8000
FRAUD_SERVICE_TIMEOUT_SECONDS=2.0
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
EOF

write_env notification-service <<EOF
SERVICE_NAME=notification-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://notification:notification@postgres:5432/notification_db
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
INTERNAL_SERVICE_TOKEN=$NOTIFICATION_TOKEN
EOF

write_env webhook-service <<EOF
SERVICE_NAME=webhook-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://webhook:webhook@postgres:5432/webhook_db
IDENTITY_SERVICE_JWKS_URL=http://identity-service:8000/.well-known/jwks.json
JWT_ISSUER=fincore-identity-service
INTERNAL_SERVICE_TOKEN=$SHARED_TOKEN
PAYMENT_SERVICE_BASE_URL=http://payment-service:8000
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
EOF

write_env audit-service <<EOF
SERVICE_NAME=audit-service
LOG_LEVEL=INFO
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4318
DATABASE_URL=postgresql+asyncpg://audit:audit@postgres:5432/audit_db
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
INTERNAL_SERVICE_TOKEN=$AUDIT_TOKEN
EOF
