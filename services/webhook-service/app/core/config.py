from fincore_common import BaseServiceSettings


class Settings(BaseServiceSettings):
    service_name: str = "webhook-service"

    # postgresql+asyncpg://user:password@host:port/webhook_db
    database_url: str

    # For verifying end-user (merchant owner) bearer tokens on the public
    # endpoint-registration API (Section 5).
    identity_service_jwks_url: str
    jwt_issuer: str = "fincore-identity-service"

    # Shared secret webhook-service sends when calling payment-service's
    # /internal/* API (Section 19), to verify merchant ownership at
    # registration time. Must match payment-service's own
    # INTERNAL_SERVICE_TOKEN.
    internal_service_token: str

    payment_service_base_url: str
    payment_service_timeout_seconds: float = 5.0

    # Kafka consumer (spec Section 14.3) — payment.completed/failed/
    # refunded are the events merchants register webhooks for; transfers
    # have no merchant_id and are out of scope here.
    kafka_bootstrap_servers: str = "localhost:9094"
    payments_topic: str = "payments"
    consumer_group_id: str = "webhook-service"

    # Delivery worker (spec Section 17) — polls due `webhook_deliveries`
    # rows and attempts them, independently of the Kafka consumer: an
    # event only needs to be turned into delivery rows once (fast,
    # in-process DB writes), while the actual HTTP delivery to a
    # merchant's endpoint has its own, much longer-lived retry schedule
    # and shouldn't hold up committing the Kafka offset.
    delivery_worker_interval_seconds: float = 5.0
    delivery_worker_batch_size: int = 100

    # Retry with backoff (spec Section 17). attempts is 1-indexed; a
    # delivery is marked terminally FAILED once it reaches this count.
    max_delivery_attempts: int = 6
    retry_base_delay_seconds: float = 5.0

    # Timeout for a single HTTP delivery attempt to a merchant's endpoint.
    delivery_timeout_seconds: float = 5.0

    # spec Section 17: "failure handling (endpoint auto-disabled after
    # repeated failures)" — counts consecutive terminally-failed
    # deliveries, reset to 0 on any success.
    disable_endpoint_after_consecutive_failures: int = 10


settings = Settings()  # type: ignore[call-arg]
