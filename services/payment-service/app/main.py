import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fincore_common import CorrelationIdMiddleware, configure_logging, register_error_handlers

from app.api.v1.transactions import router as transactions_router
from app.api.v1.transfers import router as transfers_router
from app.core import kafka as kafka_module
from app.core.config import settings
from app.db import session as db_session
from app.services.idempotency import IdempotentReplayResponse
from app.services.outbox import relay_outbox_events
from app.services.recovery import resolve_stuck_transfers

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)


async def _recovery_worker_loop() -> None:
    """Runs `resolve_stuck_transfers` on a fixed interval for the life of
    the process. One misbehaving iteration (e.g. ledger-service down for
    an extended stretch) is logged and retried next tick rather than
    killing the loop.
    """
    while True:
        await asyncio.sleep(settings.recovery_worker_interval_seconds)
        try:
            async with db_session.async_session_factory() as session:
                resolved = await resolve_stuck_transfers(
                    session, stuck_after_seconds=settings.recovery_worker_stuck_after_seconds
                )
            if resolved:
                logger.info("recovery worker resolved %d stuck transfer(s)", len(resolved))
        except Exception:
            logger.exception("recovery worker iteration failed")


async def _outbox_relay_loop() -> None:
    """Runs `relay_outbox_events` on a fixed interval for the life of the
    process (spec Section 14.1). Same failure handling as the recovery
    worker: one bad iteration (Kafka unreachable) is logged and retried
    next tick.
    """
    while True:
        await asyncio.sleep(settings.outbox_relay_interval_seconds)
        try:
            async with db_session.async_session_factory() as session:
                published = await relay_outbox_events(session, kafka_module.event_producer)
            if published:
                logger.info("outbox relay published %d event(s)", published)
        except Exception:
            logger.exception("outbox relay iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    await kafka_module.event_producer.start()
    recovery_task = asyncio.create_task(_recovery_worker_loop())
    outbox_task = asyncio.create_task(_outbox_relay_loop())
    yield
    for task in (recovery_task, outbox_task):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
    await kafka_module.event_producer.stop()
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Payment Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)


@app.exception_handler(IdempotentReplayResponse)
async def _handle_idempotent_replay(
    request: Request, exc: IdempotentReplayResponse
) -> JSONResponse:
    """Not an error path: returns the exact response an earlier request
    with this same Idempotency-Key already produced, instead of
    re-running the business logic (spec Section 9.1).
    """
    return JSONResponse(status_code=exc.status_code, content=exc.body)


app.include_router(transfers_router)
app.include_router(transactions_router)


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
