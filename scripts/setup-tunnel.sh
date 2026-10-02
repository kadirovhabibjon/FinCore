#!/usr/bin/env bash
# Gives the local stack a permanent public HTTPS link through ngrok, so it
# opens on any phone or computer, on any network, while this machine is on.
#
#   ./scripts/setup-tunnel.sh <ngrok-authtoken> <your-domain.ngrok-free.app>
#
# Both come from https://dashboard.ngrok.com (free account): "Your Authtoken",
# and "Domains" -> the one free static domain. They're written to the root
# .env (git-ignored), never to a committed file.
set -euo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <ngrok-authtoken> <domain.ngrok-free.app>" >&2
  exit 2
fi
TOKEN="$1"
DOMAIN="${2#https://}"
DOMAIN="${DOMAIN%/}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"

touch "$ENV_FILE"
chmod 600 "$ENV_FILE"
grep -vE '^(NGROK_AUTHTOKEN|NGROK_DOMAIN)=' "$ENV_FILE" > "$ENV_FILE.tmp" || true
printf 'NGROK_AUTHTOKEN=%s\nNGROK_DOMAIN=%s\n' "$TOKEN" "$DOMAIN" >> "$ENV_FILE.tmp"
mv "$ENV_FILE.tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"

cd "$ROOT"
docker compose --profile tunnel up -d ngrok
sleep 5
if docker compose --profile tunnel logs ngrok 2>&1 | grep -q "started tunnel"; then
  echo
  echo "Public link:   https://$DOMAIN"
  echo "Admin console: https://$DOMAIN/admin"
else
  echo "ngrok didn't report a running tunnel yet; check: docker compose --profile tunnel logs ngrok" >&2
  exit 1
fi
