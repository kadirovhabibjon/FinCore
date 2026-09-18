import logging
import os

# No OTLP collector runs during tests, so every test that imports
# app.main (which calls configure_tracing() at import time) would
# otherwise spam stderr with connection-refused retries from the
# exporter's background thread — harmless (spans are just dropped), but
# noisy. Silenced here rather than skipping tracing setup in tests,
# since exercising the real instrumentation call is itself part of what
# the test suite is verifying.
logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").setLevel(
    logging.CRITICAL
)

# app.core.config imports settings at module load time (Settings() requires
# DATABASE_URL). Set a syntactically valid placeholder here, before pytest
# collects any test module that imports app.main, so plain unit tests (e.g.
# /health) never need a real database. Integration tests that need a real
# database point db_session.engine at a testcontainer explicitly.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
)

# Test-only Ed25519 keypair, generated for this test suite alone — never
# used to sign anything outside pytest. Same reasoning as DATABASE_URL
# above: app.core.config needs a syntactically valid value at import time.
os.environ.setdefault(
    "JWT_PRIVATE_KEY",
    "-----BEGIN PRIVATE KEY-----\\n"
    "MC4CAQAwBQYDK2VwBCIEID/GKNrturQBs0PHh7CXec7DpXPr7cflxZx4A0dYQZw2\\n"
    "-----END PRIVATE KEY-----\\n",
)
