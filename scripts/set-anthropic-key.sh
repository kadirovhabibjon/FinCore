#!/usr/bin/env bash
# Stores a Claude API key for assistant-service and restarts it.
#
#   ./scripts/set-anthropic-key.sh
#
# Checks the key against the Claude API (a free models listing), asks for
# it without echoing it, so it never lands in the shell
# history or on screen, and writes it only to the git-ignored
# services/assistant-service/.env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/services/assistant-service/.env"
[[ -f "$ENV_FILE" ]] || "$ROOT/scripts/generate-dev-env.sh" >/dev/null

SAVED_KEY="$(grep -E '^ANTHROPIC_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)"
if [[ -n "$SAVED_KEY" ]]; then
  echo "A key is already saved. Press Enter to keep it, or paste a new one."
fi
read -rsp "API key (input is hidden): " KEY
echo
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
if [[ -z "$KEY" && -n "$SAVED_KEY" ]]; then
  KEY="$SAVED_KEY"
  echo "Keeping the saved key."
fi
if [[ "$KEY" == wrkspc_* ]]; then
  echo "That's a workspace id, not the API key. You'll be asked for it next; run again." >&2
  exit 1
fi
if [[ "$KEY" != sk-ant-* ]]; then
  echo "That doesn't look like a Claude API key (it should start with sk-ant-)." >&2
  echo "Create one at https://platform.claude.com/settings/keys -> Create key." >&2
  exit 1
fi

# A user key ("sk-ant-usr-...") isn't tied to a workspace: the API then
# needs the workspace id on every request.
WORKSPACE=""
if [[ "$KEY" == sk-ant-usr-* ]]; then
  echo "This is a user key: it also needs the workspace to use."
  echo "Find it at https://platform.claude.com -> Settings -> Workspaces (starts with wrkspc_)."
  read -rp "Workspace id: " WORKSPACE
  WORKSPACE="$(printf '%s' "$WORKSPACE" | tr -d '[:space:]')"
  if [[ "$WORKSPACE" != wrkspc_* ]]; then
    echo "A workspace id starts with wrkspc_." >&2
    exit 1
  fi
fi

# Ask the API whether the key works before saving it. Listing models is
# free; the key goes in a header read from stdin, never on the command line.
workspace_header=()
[[ -n "$WORKSPACE" ]] && workspace_header=(-H "anthropic-workspace-id: $WORKSPACE")
status="$(printf 'header = "x-api-key: %s"\n' "$KEY" | curl -sS -o /dev/null -w '%{http_code}' \
  --config - -H 'anthropic-version: 2023-06-01' "${workspace_header[@]}" \
  https://api.anthropic.com/v1/models || true)"
case "$status" in
  200) echo "The Claude API accepted the key." ;;
  401) echo "The Claude API rejected this key (401). Create a new one and try again." >&2; exit 1 ;;
  *)   echo "Couldn't verify the key (HTTP $status); saving it anyway." >&2 ;;
esac

tmp="$(mktemp)"
grep -vE '^ANTHROPIC_(API_KEY|WORKSPACE_ID)=' "$ENV_FILE" > "$tmp" || true
printf 'ANTHROPIC_API_KEY=%s\nANTHROPIC_WORKSPACE_ID=%s\n' "$KEY" "$WORKSPACE" >> "$tmp"
mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset KEY

cd "$ROOT"
docker compose up -d --build --force-recreate --wait assistant-service >/dev/null
echo "Saved. assistant-service: $(curl -fsS http://localhost:8099/ready)"
