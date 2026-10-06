#!/usr/bin/env bash
# Lets identity-service send password-reset codes by email, then restarts it.
#
#   ./scripts/set-smtp.sh
#
# Made for Gmail (free): the address the codes are sent from, and an "app
# password" for it - not the account's normal password. To create one:
#   1. turn on 2-Step Verification: https://myaccount.google.com/security
#   2. create an app password:      https://myaccount.google.com/apppasswords
# Any other SMTP server with STARTTLS works too (you are asked for the host).
#
# The password is asked for without echoing it, so it never lands in the
# shell history or on screen; it is checked by signing in to the mail
# server and written only to the git-ignored services/identity-service/.env.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/services/identity-service/.env"
[[ -f "$ENV_FILE" ]] || "$ROOT/scripts/generate-dev-env.sh" >/dev/null

read -rp "Email address to send from (e.g. you@gmail.com): " ADDRESS
ADDRESS="$(printf '%s' "$ADDRESS" | tr -d '[:space:]')"
if [[ "$ADDRESS" != *@*.* ]]; then
  echo "That doesn't look like an email address." >&2
  exit 1
fi

HOST="smtp.gmail.com"
if [[ "$ADDRESS" != *@gmail.com && "$ADDRESS" != *@googlemail.com ]]; then
  read -rp "SMTP server for this address (STARTTLS on port 587): " HOST
  HOST="$(printf '%s' "$HOST" | tr -d '[:space:]')"
  [[ -n "$HOST" ]] || { echo "No server entered." >&2; exit 1; }
fi

read -rsp "App password (input is hidden): " PASSWORD
echo
# Google shows app passwords in groups of four separated by spaces.
PASSWORD="$(printf '%s' "$PASSWORD" | tr -d '[:space:]')"
if [[ -z "$PASSWORD" ]]; then
  echo "No password entered." >&2
  exit 1
fi

# Sign in to the mail server before saving anything. The password goes to
# the checker on stdin, never on a command line.
echo "Checking with $HOST ..."
if ! printf '%s' "$PASSWORD" | SMTP_CHECK_HOST="$HOST" SMTP_CHECK_USER="$ADDRESS" python3 -c '
import os, smtplib, ssl, sys
password = sys.stdin.read()
try:
    with smtplib.SMTP(os.environ["SMTP_CHECK_HOST"], 587, timeout=20) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(os.environ["SMTP_CHECK_USER"], password)
except smtplib.SMTPAuthenticationError:
    sys.exit("The mail server rejected this address and password. For Gmail it must be an"
             " app password (https://myaccount.google.com/apppasswords), not your normal one.")
except Exception as exc:
    sys.exit(f"Could not reach the mail server: {type(exc).__name__}")
'; then
  exit 1
fi
echo "The mail server accepted the sign-in."

tmp="$(mktemp)"
grep -vE '^SMTP_(HOST|PORT|USERNAME|PASSWORD|FROM)=' "$ENV_FILE" > "$tmp" || true
printf 'SMTP_HOST=%s\nSMTP_PORT=587\nSMTP_USERNAME=%s\nSMTP_PASSWORD=%s\nSMTP_FROM=FinCore <%s>\n' \
  "$HOST" "$ADDRESS" "$PASSWORD" "$ADDRESS" >> "$tmp"
mv "$tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
unset PASSWORD

cd "$ROOT"
docker compose up -d --build --force-recreate --wait identity-service >/dev/null
echo "Saved. Password reset codes will be sent from $ADDRESS."
