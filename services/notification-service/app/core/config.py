from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "notification-service"

    # postgresql+asyncpg://user:password@host:port/notification_db
    database_url: str

    kafka_bootstrap_servers: str = "localhost:9094"
    transfers_topic: str = "transfers"
    # A distinct group id per logical consumer — Kafka tracks committed
    # offsets per (group_id, topic, partition), so this is what lets a
    # restarted notification-service resume where it left off instead of
    # replaying the whole topic.
    consumer_group_id: str = "notification-service"

    # Retry / DLT (spec Section 16). retry_topic gets its own consumer
    # group id derived from consumer_group_id, not a separate setting —
    # see app/core/kafka.py.
    retry_topic: str = "transfers-retry"
    dlt_topic: str = "transfers-dlt"
    max_retry_attempts: int = 3
    retry_base_delay_seconds: float = 2.0

    # Shared secret for /internal/* endpoints (Section 19) — the manual
    # dead-letter replay API (app/api/internal/dead_letters.py).
    internal_service_token: str


settings = Settings()  # type: ignore[call-arg]
