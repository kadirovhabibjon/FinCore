import os

# app.core.config imports settings at module load time. Set a
# syntactically valid placeholder here, before pytest collects any test
# module that imports app.main, so plain unit tests never need real
# infrastructure. Integration tests point at real dependencies
# explicitly instead.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://placeholder:placeholder@localhost:5432/placeholder",
)
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-only-internal-token")
