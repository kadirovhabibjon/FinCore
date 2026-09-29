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

from app.api.internal.risk_checks import router as risk_checks_router
from app.core import kafka as kafka_module
from app.core.config import settings
from app.db import session as db_session
from app.services.outbox import drain_outbox

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)


async def _outbox_relay_loop() -> None:
    """Publishes fraud events for the life of the process. The producer
    is started here, with retries, not in the lifespan: payment-service
    calls this service on every transfer and payment, so it must keep
    scoring while Kafka is down. Events wait in the outbox meanwhile
    (same approach as identity-service).
    """
    producer = kafka_module.event_producer
    started = False
    try:
        while True:
            await asyncio.sleep(settings.outbox_relay_interval_seconds)
            try:
                if not started:
                    await producer.start()
                    started = True
                published = await drain_outbox(producer)
                if published:
                    logger.info("outbox relay published %d event(s)", published)
            except Exception:
                logger.exception("outbox relay iteration failed")
                if started:
                    continue
                # A failed start can leave a half-built client behind.
                with contextlib.suppress(Exception):
                    await producer.stop()
    finally:
        if started:
            await producer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    relay_task = asyncio.create_task(_outbox_relay_loop())
    yield
    relay_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await relay_task
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Fraud Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
configure_tracing(
    service_name=settings.service_name, otlp_endpoint=settings.otel_exporter_otlp_endpoint, app=app
)
configure_metrics(app, service_name=settings.service_name)
app.include_router(risk_checks_router)


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
