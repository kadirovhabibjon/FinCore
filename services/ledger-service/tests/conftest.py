import os

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
