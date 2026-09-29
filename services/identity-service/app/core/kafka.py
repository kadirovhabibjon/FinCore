from fincore_common.kafka import EventProducer

from app.core.config import settings

# One producer for the process, started/stopped in app/main.py's
# lifespan — the same shape as payment-service's app/core/kafka.py.
event_producer = EventProducer(settings.kafka_bootstrap_servers)
