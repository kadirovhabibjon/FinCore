#!/bin/sh
set -e

# Applying migrations on container start is a v0.1/single-instance choice
# (docker-compose runs exactly one identity-service replica). Once there
# are multiple replicas, this moves to a separate one-shot migrate job so
# N starting containers don't race to run migrations concurrently.
alembic upgrade head

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
