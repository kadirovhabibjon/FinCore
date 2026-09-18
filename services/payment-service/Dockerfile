# Build context is the monorepo root (see docker-compose.yml), not this
# directory — needed so this Dockerfile can reach libs/fincore-common.
FROM python:3.12-slim

WORKDIR /app

COPY libs/fincore-common ./libs/fincore-common
RUN pip install --no-cache-dir ./libs/fincore-common

COPY services/payment-service ./services/payment-service
RUN pip install --no-cache-dir ./services/payment-service

WORKDIR /app/services/payment-service
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
