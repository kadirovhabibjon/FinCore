from fincore_common.kafka import EventConsumer

from app.core.config import settings

# Started/stopped in app/main.py's lifespan. No EventProducer here —
# unlike notification-service, webhook-service never republishes to
# Kafka: a failed delivery is retried by the delivery worker
# (app/services/delivery.py) against `webhook_deliveries.next_attempt_at`,
# not routed through a retry/DLT topic.
event_consumer = EventConsumer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topics=[settings.payments_topic],
    group_id=settings.consumer_group_id,
)
