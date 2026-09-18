from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.sdk.resources import SERVICE_NAME, Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_httpx_instrumented = False


def configure_tracing(*, service_name: str, otlp_endpoint: str, app: FastAPI) -> None:
    """One-time OpenTelemetry setup (spec Section 24: distributed tracing
    is required from the start of multi-service work, unlike Prometheus/
    Grafana which the spec explicitly defers to later). Exports spans to
    an OTLP HTTP collector — Jaeger in docker-compose.

    Spans are queued and flushed by a background thread
    (`BatchSpanProcessor`); a collector that's briefly unreachable (e.g.
    in tests, which never run one) degrades to dropped spans, never a
    blocked or failed request — tracing is a side channel, not something
    request handling depends on.
    """
    global _httpx_instrumented

    provider = TracerProvider(resource=Resource.create({SERVICE_NAME: service_name}))
    provider.add_span_processor(
        BatchSpanProcessor(OTLPSpanExporter(endpoint=f"{otlp_endpoint}/v1/traces"))
    )
    trace.set_tracer_provider(provider)

    FastAPIInstrumentor.instrument_app(app)

    if not _httpx_instrumented:
        # Global, not per-instance: every service in this codebase
        # constructs a fresh httpx.AsyncClient per call (see
        # ledger-service/payment-service's internal HTTP clients) rather
        # than reusing one, so instrumenting a specific instance isn't
        # an option — HTTPXClientInstrumentor patches the transport
        # class itself, which covers every client created afterward.
        HTTPXClientInstrumentor().instrument()
        _httpx_instrumented = True
