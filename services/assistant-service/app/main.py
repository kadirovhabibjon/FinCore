import logging

from fastapi import FastAPI
from fincore_common import (
    CorrelationIdMiddleware,
    configure_logging,
    configure_metrics,
    configure_tracing,
    register_error_handlers,
)

from app.api.v1.chat import router as chat_router
from app.core.config import settings

configure_logging(service_name=settings.service_name, level=settings.log_level)
logger = logging.getLogger(__name__)

app = FastAPI(title="FinCore Assistant Service", version="0.1.0")
app.add_middleware(CorrelationIdMiddleware)
register_error_handlers(app)
configure_tracing(
    service_name=settings.service_name, otlp_endpoint=settings.otel_exporter_otlp_endpoint, app=app
)
configure_metrics(app, service_name=settings.service_name)
app.include_router(chat_router)


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness: is the process up."""
    return {"status": "ok"}


@app.get("/ready")
async def ready() -> dict[str, str]:
    """No database or broker to check. Reports whether a Claude API key is
    configured, but stays ready without one: the rest of FinCore doesn't
    depend on the assistant, and the chat endpoint explains the 503."""
    configured = "configured" if settings.anthropic_api_key else "not configured"
    return {"status": "ok", "assistant": configured}
