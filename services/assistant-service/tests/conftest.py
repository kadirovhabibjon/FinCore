import logging
import os

logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").setLevel(
    logging.CRITICAL
)

# Settings load at import time; syntactically valid placeholders so no
# test needs real infrastructure. No Anthropic key: tests inject a fake
# Claude API transport explicitly.
os.environ.setdefault("IDENTITY_SERVICE_JWKS_URL", "http://placeholder/.well-known/jwks.json")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
# A developer's own .env may select a provider and hold a real key
# (scripts/set-assistant-key.sh): the tests must never use either.
os.environ["ASSISTANT_PROVIDER"] = "anthropic"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ANTHROPIC_WORKSPACE_ID"] = ""
os.environ["LLM_API_KEY"] = ""
os.environ["ASSISTANT_MODEL"] = "claude-opus-5-5"
os.environ["ASSISTANT_EFFORT"] = "medium"
