from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "audit-service"

    # postgresql+asyncpg://user:password@host:port/audit_db
    database_url: str

    # Kafka consumer (spec Section 14.3) — every domain event currently
    # published is audit-worthy on its own terms (spec Section 18's
    # TRANSFER_COMPLETED/TRANSFER_FAILED examples map directly; payment
    # events aren't in the spec's example list by name but are the same
    # kind of fact). One consumer subscribes to both topics — this
    # service doesn't need per-aggregate-type partitioning of its own,
    # it just records what already happened.
    kafka_bootstrap_servers: str = "localhost:9094"
    transfers_topic: str = "transfers"
    payments_topic: str = "payments"
    # identity-service's account events (registration, status and role
    # changes) — spec Section 18's USER_BLOCKED / ADMIN_ACTION.
    users_topic: str = "users"
    consumer_group_id: str = "audit-service"

    # Retry / DLT (spec Section 16) — losing an audit record silently is
    # worse than losing a notification, so a malformed or unprocessable
    # event still needs somewhere to land besides an infinitely-retried,
    # partition-blocking loop.
    retry_topic: str = "audit-retry"
    dlt_topic: str = "audit-dlt"
    max_retry_attempts: int = 3
    retry_base_delay_seconds: float = 2.0

    # Shared secret for /internal/* endpoints (Section 19) — the
    # read-only audit-log query API and the dead-letter replay API.
    internal_service_token: str


settings = Settings()  # type: ignore[call-arg]
