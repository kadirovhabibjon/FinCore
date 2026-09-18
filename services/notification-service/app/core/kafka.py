from fincore_common.kafka import EventConsumer

from app.core.config import settings

# One consumer for the process, started/stopped in app/main.py's
# lifespan — the same shape as payment-service's app/core/kafka.py.
event_consumer = EventConsumer(
    bootstrap_servers=settings.kafka_bootstrap_servers,
    topics=[settings.transfers_topic],
    group_id=settings.consumer_group_id,
)
