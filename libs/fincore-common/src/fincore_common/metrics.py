import time

from fastapi import FastAPI, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Registered once per process, not per service instance — every service
# is its own process, so there's exactly one of these per service
# anyway. Labeled by `service`, not split into separate registries per
# service, so Prometheus can compare across services on one query (spec
# Section 24's "HTTP request count (per service)").
HTTP_REQUESTS_TOTAL = Counter(
    "fincore_http_requests_total",
    "Total HTTP requests handled.",
    ["service", "method", "path", "status_code"],
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "fincore_http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["service", "method", "path"],
)

# Re-exported so a service's own domain metrics (spec Section 24's
# "payment count," "outbox backlog," "DLT message count," ...) use the
# same `prometheus_client` types and share this module's default
# registry, without every service adding its own dependency on
# `prometheus_client` directly.
__all__ = [
    "Counter",
    "Gauge",
    "Histogram",
    "configure_metrics",
    "HTTP_REQUESTS_TOTAL",
    "HTTP_REQUEST_DURATION_SECONDS",
]

# Excluded from the HTTP metrics above — not because they're
# uninteresting, but because a Prometheus scrape hitting /metrics every
# few seconds would otherwise dominate every other route's own counts.
_UNMETERED_PATHS = frozenset({"/metrics"})


class _PrometheusMiddleware:
    """Pure ASGI middleware, not `BaseHTTPMiddleware`: this runs on
    every single request rather than a handful of times per app
    lifetime, so it avoids `BaseHTTPMiddleware`'s known overhead and its
    documented interactions with streaming responses and background
    tasks. The route's path *template* (`/api/v1/payments/{payment_id}`,
    not the literal request path) comes from `scope["route"]`, set by
    Starlette's router before the endpoint runs — using the raw path
    instead would blow up label cardinality with one time series per
    distinct id ever requested.
    """

    def __init__(self, app: ASGIApp, *, service_name: str) -> None:
        self._app = app
        self._service_name = service_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return

        status_code = 0

        async def _send(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        start = time.perf_counter()
        await self._app(scope, receive, _send)
        duration = time.perf_counter() - start

        route = scope.get("route")
        path = route.path if route is not None else scope["path"]
        if path in _UNMETERED_PATHS:
            return

        method = scope["method"]
        HTTP_REQUESTS_TOTAL.labels(
            service=self._service_name, method=method, path=path, status_code=str(status_code)
        ).inc()
        HTTP_REQUEST_DURATION_SECONDS.labels(
            service=self._service_name, method=method, path=path
        ).observe(duration)


def configure_metrics(app: FastAPI, *, service_name: str) -> None:
    """One-time Prometheus setup (spec Section 24, deferred relative to
    tracing per that section's own "later add" split — see
    tracing.py's docstring). Adds the ASGI middleware above and mounts
    `GET /metrics` in Prometheus text exposition format.
    """
    app.add_middleware(_PrometheusMiddleware, service_name=service_name)

    @app.get("/metrics", include_in_schema=False)
    async def _metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
