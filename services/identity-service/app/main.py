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

from app.api.v1.auth import router as auth_router
from app.api.v1.users import router as users_router
from app.api.well_known import router as well_known_router
from app.core.config import settings
from app.db import session as db_session

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await db_session.engine.dispose()


app = FastAPI(
    title="FinCore Identity Service",
    version="0.1.0",
    lifespan=lifespan,
)
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
configure_tracing(
    service_name=settings.service_name, otlp_endpoint=settings.otel_exporter_otlp_endpoint, app=app
)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(well_known_router)


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
