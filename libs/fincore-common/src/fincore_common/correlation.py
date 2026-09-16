from __future__ import annotations

import uuid
from contextvars import ContextVar, Token

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

HEADER_NAME = "X-Correlation-ID"

_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)


def get_correlation_id() -> str | None:
    """Return the correlation ID for the request currently being handled.

    Returns None outside of a request (e.g. in a startup hook or a worker
    loop iteration that hasn't set one).
    """
    return _correlation_id.get()


def set_correlation_id(value: str) -> Token[str | None]:
    return _correlation_id.set(value)


def reset_correlation_id(token: Token[str | None]) -> None:
    _correlation_id.reset(token)


def new_correlation_id() -> str:
    return str(uuid.uuid4())


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Propagates a correlation ID through the request.

    Reuses the incoming `X-Correlation-ID` header if the gateway (or a
    calling service) already set one, otherwise generates a new one. Either
    way, the ID is stored in a ContextVar for the duration of the request
    (so `configure_logging`'s JSON formatter can attach it to every log
    line) and echoed back in the response header.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        correlation_id = request.headers.get(HEADER_NAME) or new_correlation_id()
        token = set_correlation_id(correlation_id)
        try:
            response = await call_next(request)
        finally:
            reset_correlation_id(token)
        response.headers[HEADER_NAME] = correlation_id
        return response
