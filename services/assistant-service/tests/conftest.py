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
