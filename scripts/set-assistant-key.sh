#!/usr/bin/env bash
# Connects the assistant chat to a free model API and restarts it.
#
#   ./scripts/set-assistant-key.sh
#
# Takes a Google Gemini key (https://aistudio.google.com/apikey) or a Groq
# key (https://console.groq.com/keys, starts with gsk_); both are free and
# need no card. The key is asked for without echoing it, so it never lands
# in the shell history or on screen, is checked against the provider, and
# is written only to the git-ignored services/assistant-service/.env.
# (For a paid Claude key use ./scripts/set-anthropic-key.sh instead.)
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/services/assistant-service/.env"
[[ -f "$ENV_FILE" ]] || "$ROOT/scripts/generate-dev-env.sh" >/dev/null

SAVED_KEY="$(grep -E '^LLM_API_KEY=' "$ENV_FILE" | cut -d= -f2- || true)"
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
if [[ -z "$KEY" ]]; then
  echo "No key entered." >&2
  exit 1
fi
if [[ "$KEY" == sk-ant-* ]]; then
  echo "That's a Claude key: use ./scripts/set-anthropic-key.sh for it." >&2
  exit 1
fi

# Models to use, best first: the first one this key can see answers, the
# others are fallbacks for when it is overloaded or over its free quota.
if [[ "$KEY" == gsk_* ]]; then
  PROVIDER="Groq"
  BASE_URL="https://api.groq.com/openai/v1"
  MODELS_URL="https://api.groq.com/openai/v1/models"
  AUTH_HEADER="Authorization: Bearer $KEY"
  PREFERRED="openai/gpt-oss-120b llama-3.3-70b-versatile openai/gpt-oss-20b"
else
  PROVIDER="Google Gemini"
  BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai"
  MODELS_URL="https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
  AUTH_HEADER="x-goog-api-key: $KEY"
  PREFERRED="gemini-flash-latest gemini-flash-lite-latest gemini-3.1-flash-lite"
fi

# Ask the provider for its model list: free, and it proves the key works.
# The key goes in a header read from stdin, never on the command line.
listing="$(mktemp)"
trap 'rm -f "$listing"' EXIT
status="$(printf 'header = "%s"\n' "$AUTH_HEADER" | curl -sS -o "$listing" -w '%{http_code}' \
  --max-time 20 --config - "$MODELS_URL" || true)"
case "$status" in
  200) echo "$PROVIDER accepted the key." ;;
  400|401|403)
    echo "$PROVIDER rejected this key (HTTP $status). Create a new one and try again." >&2
    exit 1 ;;
  *) echo "Couldn't reach $PROVIDER to check the key (HTTP $status). Try again." >&2; exit 1 ;;
esac

AVAILABLE="$(PREFERRED="$PREFERRED" python3 - "$listing" <<'PYEOF'
import json, os, sys
data = json.load(open(sys.argv[1]))
ids = {m.get("id") or m.get("name", "").removeprefix("models/")
       for m in data.get("data") or data.get("models") or []}
print(" ".join(m for m in os.environ["PREFERRED"].split() if m in ids))
PYEOF
)"
MODEL="${AVAILABLE%% *}"
FALLBACKS="$(printf '%s' "${AVAILABLE#"$MODEL"}" | xargs | tr ' ' ',')"
if [[ -z "$MODEL" ]]; then
  echo "None of the expected models ($PREFERRED) is available to this key." >&2
  echo "Set ASSISTANT_PROVIDER, LLM_BASE_URL, LLM_MODEL and LLM_API_KEY in $ENV_FILE by hand." >&2
  exit 1
fi
echo "Model: $MODEL${FALLBACKS:+ (fallbacks: $FALLBACKS)}"

tmp="$(mktemp)"
grep -vE '^(ASSISTANT_PROVIDER|LLM_API_KEY|LLM_BASE_URL|LLM_MODEL|LLM_FALLBACK_MODELS)=' "$ENV_FILE" > "$tmp" || true
printf 'ASSISTANT_PROVIDER=openai_compatible\nLLM_BASE_URL=%s\nLLM_MODEL=%s\nLLM_FALLBACK_MODELS=%s\nLLM_API_KEY=%s\n' \
  "$BASE_URL" "$MODEL" "$FALLBACKS" "$KEY" >> "$tmp"
mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset KEY AUTH_HEADER

cd "$ROOT"
docker compose up -d --build --force-recreate --wait assistant-service >/dev/null
echo "Saved. assistant-service: $(curl -fsS http://localhost:8099/ready)"
