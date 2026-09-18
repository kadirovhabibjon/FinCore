# Build context is the monorepo root (see docker-compose.yml), not this
# directory — needed so this Dockerfile can reach libs/fincore-common.
FROM python:3.12-slim

WORKDIR /app

COPY libs/fincore-common ./libs/fincore-common
RUN pip install --no-cache-dir "./libs/fincore-common[kafka]"

COPY services/notification-service ./services/notification-service
RUN pip install --no-cache-dir ./services/notification-service

WORKDIR /app/services/notification-service
EXPOSE 8000

ENTRYPOINT ["./entrypoint.sh"]
