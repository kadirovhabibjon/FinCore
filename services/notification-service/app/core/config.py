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


settings = Settings()  # type: ignore[call-arg]
