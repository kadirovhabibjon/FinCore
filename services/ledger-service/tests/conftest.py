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

# app.core.config imports settings at module load time (Settings()
# requires DATABASE_URL). Set a syntactically valid placeholder here,
# before pytest collects any test module that imports app.main, so plain
# unit tests never need a real database. Integration tests point
# db_session.engine at a testcontainer explicitly instead.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
)
os.environ.setdefault(
    "IDENTITY_SERVICE_JWKS_URL", "http://placeholder/.well-known/jwks.json"
)
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-only-internal-token")
