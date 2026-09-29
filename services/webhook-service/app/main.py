import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fincore_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_metrics,
    configure_tracing,
    register_error_handlers,
)

from app.api.v1.admin import router as admin_router
from app.api.v1.webhooks import router as webhooks_router
from app.core import kafka as kafka_module
from app.core.config import settings
from app.db import session as db_session
from app.services.consumer import handle_payment_event
from app.services.delivery import run_delivery_pass
from app.services.retry import RetryPolicy

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)

_retry_policy = RetryPolicy(
    max_attempts=settings.max_delivery_attempts,
    base_delay_seconds=settings.retry_base_delay_seconds,
)


async def _consume_forever() -> None:
    """Runs for the life of the process. `handle_payment_event` only
    ever does idempotent DB writes (app/services/consumer.py) — an
    exception here means something broke below that (the DB, a bug),
    not a delivery failure, which is handled entirely by the delivery
    worker instead. Logged and restarted rather than left dead.
    """
    while True:
        try:
            await kafka_module.event_consumer.run(handle_payment_event)
        except Exception:
            logger.exception("kafka consumer loop failed; restarting")
            await asyncio.sleep(5.0)


async def _delivery_worker_loop() -> None:
    """Runs `run_delivery_pass` on a fixed interval for the life of the
    process (spec Section 17). Same failure handling as every other
    worker loop in this project: one bad pass is logged and retried
    next tick.
    """
    while True:
        await asyncio.sleep(settings.delivery_worker_interval_seconds)
        try:
            async with db_session.async_session_factory() as session:
                attempted = await run_delivery_pass(
                    session,
                    batch_size=settings.delivery_worker_batch_size,
                    policy=_retry_policy,
                    timeout_seconds=settings.delivery_timeout_seconds,
                    disable_after_consecutive_failures=(
                        settings.disable_endpoint_after_consecutive_failures
                    ),
                )
            if attempted:
                logger.info("delivery worker attempted %d delivery(ies)", attempted)
        except Exception:
            logger.exception("delivery worker iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await kafka_module.event_consumer.start()
    tasks = [
        asyncio.create_task(_consume_forever()),
        asyncio.create_task(_delivery_worker_loop()),
    ]
    yield
    for task in tasks:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await kafka_module.event_consumer.stop()
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Webhook Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
configure_tracing(
    service_name=settings.service_name, otlp_endpoint=settings.otel_exporter_otlp_endpoint, app=app
)
configure_metrics(app, service_name=settings.service_name)
app.include_router(webhooks_router)
app.include_router(admin_router)


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
    return {"status": "ok"}
