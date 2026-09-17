# Build context is the monorepo root (see docker-compose.yml), not this
# directory — needed so this Dockerfile can reach libs/fincore-common,
# which lives outside services/identity-service.
FROM python:3.12-slim

WORKDIR /app

# fincore-common as its own layer: rebuilds only when the shared library
# itself changes, not on every identity-service code edit.
COPY libs/fincore-common ./libs/fincore-common
RUN pip install --no-cache-dir ./libs/fincore-common

COPY services/identity-service ./services/identity-service
RUN pip install --no-cache-dir ./services/identity-service

WORKDIR /app/services/identity-service
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
