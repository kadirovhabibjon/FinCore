import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fincore_common import CorrelationIdMiddleware, configure_logging, register_error_handlers

from app.core import kafka as kafka_module
from app.core.config import settings
from app.db import session as db_session
from app.services.consumer import handle_transfer_event
from app.services.providers import default_providers

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)

_providers = default_providers()


async def _consume_forever() -> None:
    """Runs for the life of the process. A handler exception (a bug, or
    a downstream provider outage) is logged and the loop restarts from
    where the consumer's own offset tracking left off — the failed
    message was never committed (fincore_common.kafka.EventConsumer),
    so it's retried rather than silently skipped.
    """
    while True:
        try:
            await kafka_module.event_consumer.run(
                lambda envelope: handle_transfer_event(envelope, _providers)
            )
        except Exception:
            logger.exception("consumer loop failed; restarting")
            await asyncio.sleep(5.0)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await kafka_module.event_consumer.start()
    consumer_task = asyncio.create_task(_consume_forever())
    yield
    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    await kafka_module.event_consumer.stop()
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Notification Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: is the process up. No dependency checks."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """Readiness: can the service actually serve traffic (DB reachable)."""
    try:
        await db_session.check_database_connection()
    except Exception as exc:
        logger.warning("readiness check failed: database unreachable")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database unreachable",
        ) from exc
    return {"status": "ok"}
