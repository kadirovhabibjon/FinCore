import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fincore_common import (
    CorrelationIdMiddleware,
    EventEnvelope,
    configure_logging,
    configure_tracing,
    register_error_handlers,
)
from fincore_common.kafka import EventConsumer, EventHandler

from app.api.internal.dead_letters import router as dead_letters_router
from app.core import kafka as kafka_module
from app.core.config import settings
from app.db import session as db_session
from app.services.dispatch import process_retry_topic_message, process_with_retry_routing
from app.services.providers import default_providers
from app.services.retry import RetryPolicy

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)

_providers = default_providers()
_retry_policy = RetryPolicy(
    max_attempts=settings.max_retry_attempts, base_delay_seconds=settings.retry_base_delay_seconds
)


async def _handle_main_topic_message(envelope: EventEnvelope) -> None:
    await process_with_retry_routing(
        envelope,
        attempt=1,
        providers=_providers,
        side_channel_producer=kafka_module.side_channel_producer,
        retry_topic=settings.retry_topic,
        dlt_topic=settings.dlt_topic,
        policy=_retry_policy,
    )


async def _handle_retry_topic_message(envelope: EventEnvelope) -> None:
    await process_retry_topic_message(
        envelope,
        providers=_providers,
        side_channel_producer=kafka_module.side_channel_producer,
        retry_topic=settings.retry_topic,
        dlt_topic=settings.dlt_topic,
        policy=_retry_policy,
    )


async def _consume_forever(name: str, consumer: EventConsumer, handler: EventHandler) -> None:
    """Runs for the life of the process. `process_with_retry_routing` /
    `process_retry_topic_message` never raise for a message-level
    failure (they route it to the retry topic or the DLT instead), so
    reaching this `except` means something broke below that — the
    consumer connection itself, a bug in the routing code. Logged and
    restarted rather than left dead.
    """
    while True:
        try:
            await consumer.run(handler)
        except Exception:
            logger.exception("%s consumer loop failed; restarting", name)
            await asyncio.sleep(5.0)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await kafka_module.event_consumer.start()
    await kafka_module.retry_consumer.start()
    await kafka_module.side_channel_producer.start()
    tasks = [
        asyncio.create_task(
            _consume_forever("main", kafka_module.event_consumer, _handle_main_topic_message)
        ),
        asyncio.create_task(
            _consume_forever("retry", kafka_module.retry_consumer, _handle_retry_topic_message)
        ),
    ]
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await kafka_module.event_consumer.stop()
    await kafka_module.retry_consumer.stop()
    await kafka_module.side_channel_producer.stop()
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Notification Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
configure_tracing(
    service_name=settings.service_name, otlp_endpoint=settings.otel_exporter_otlp_endpoint, app=app
)
app.include_router(dead_letters_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: is the process up. No dependency checks."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness: can the service actually serve traffic (spec Section
    24: DB and Kafka connectivity, not just liveness).
    """
    try:
        await db_session.check_database_connection()
    except Exception as exc:
        logger.warning("readiness check failed: database unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable",
        ) from exc
    try:
        await kafka_module.side_channel_producer.check_connection()
    except Exception as exc:
        logger.warning("readiness check failed: kafka unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="kafka unreachable",
        ) from exc
    return {"status": "ok"}
