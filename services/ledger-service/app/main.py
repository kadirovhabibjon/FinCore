import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, status
from fincore_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_tracing,
    register_error_handlers,
)

from app.api.internal.holds import router as internal_holds_router
from app.api.internal.postings import router as internal_postings_router
from app.api.internal.reconciliation import router as internal_reconciliation_router
from app.api.v1.wallets import router as wallets_router
from app.core.config import settings
from app.db import session as db_session
from app.services.reconciliation import run_reconciliation

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)


async def _reconciliation_loop() -> None:
    """Runs `run_reconciliation` on a fixed interval for the life of the
    process (spec Section 8.4). A violation is logged (run_reconciliation
    itself logs at ERROR) and left for a human to investigate — this loop
    never auto-corrects anything (ADR-0002). One failed iteration (e.g. a
    transient DB blip) is logged and retried next tick, not fatal.
    """
    while True:
        await asyncio.sleep(settings.reconciliation_interval_seconds)
        try:
            async with db_session.async_session_factory() as session:
                await run_reconciliation(session)
        except Exception:
            logger.exception("reconciliation iteration failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    worker_task = asyncio.create_task(_reconciliation_loop())
    yield
    worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await worker_task
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Ledger Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
configure_tracing(
    service_name=settings.service_name, otlp_endpoint=settings.otel_exporter_otlp_endpoint, app=app
)
app.include_router(wallets_router)
app.include_router(internal_postings_router)
app.include_router(internal_holds_router)
app.include_router(internal_reconciliation_router)


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
