import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fincore_common import CorrelationIdMiddleware, configure_logging, register_error_handlers

from app.core.config import settings
from app.db import session as db_session
from app.services.idempotency import IdempotentReplayResponse

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
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
