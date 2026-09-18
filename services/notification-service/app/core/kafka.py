from fincore_common.kafka import EventConsumer, EventProducer

from app.core.config import settings

# Started/stopped in app/main.py's lifespan — the same shape as
# payment-service's app/core/kafka.py.

event_consumer = EventConsumer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topics=[settings.transfers_topic],
    group_id=settings.consumer_group_id,
)

retry_consumer = EventConsumer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topics=[settings.retry_topic],
    group_id=f"{settings.consumer_group_id}-retry",
)

# Shared by both the main and retry consumer loops for publishing a
# failed event onward (to the retry topic, or the DLT — spec Section
# 16). No producer-side reason to keep these separate.
side_channel_producer = EventProducer(settings.kafka_bootstrap_servers)
