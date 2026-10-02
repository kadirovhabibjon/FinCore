# Build context is the monorepo root (see docker-compose.yml), not this
# directory — needed so this Dockerfile can reach libs/fincore-common.
FROM python:3.12-slim

WORKDIR /app

COPY libs/fincore-common ./libs/fincore-common
RUN pip install --no-cache-dir ./libs/fincore-common

COPY services/assistant-service ./services/assistant-service
RUN pip install --no-cache-dir ./services/assistant-service

WORKDIR /app/services/assistant-service
EXPOSE 8000

# No database, so no migrations to run first.
ENTRYPOINT ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
