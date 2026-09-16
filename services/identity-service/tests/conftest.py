import os

# app.core.config imports settings at module load time (Settings() requires
# DATABASE_URL). Set a syntactically valid placeholder here, before pytest
# collects any test module that imports app.main, so plain unit tests (e.g.
# /health) never need a real database. Integration tests that need a real
# database point db_session.engine at a testcontainer explicitly.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
)
