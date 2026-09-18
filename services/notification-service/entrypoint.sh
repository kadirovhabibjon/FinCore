#!/bin/sh
set -e

# See identity-service/entrypoint.sh for why this runs here (v0.1,
# single-instance) instead of a separate one-shot migrate job.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
