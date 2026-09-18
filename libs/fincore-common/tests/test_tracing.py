import asyncio
import logging

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from fincore_common.tracing import configure_tracing

# No OTLP collector runs in tests — configure_tracing() still points at
# one (spec Section 24 requires tracing be configured, not skipped, in
# every environment); its background export thread just fails quietly.
logging.getLogger("opentelemetry.exporter.otlp.proto.http.trace_exporter").setLevel(
    logging.CRITICAL
)


def test_configure_tracing_instruments_the_app_and_serves_requests_normally() -> None:
    """The primary risk in configure_tracing() is that instrumenting the
    app somehow breaks it — this proves a request still gets a normal
    response with instrumentation active, and that a span actually gets
    produced for it.

    OpenTelemetry's global TracerProvider can only be set once per
    process (a second `set_tracer_provider` call elsewhere — e.g.
    another test module — is a silent no-op), so this attaches an
    in-memory exporter to *whichever* provider ends up globally active
    rather than assuming configure_tracing()'s own call won that race;
    either way, FastAPI's instrumentation reads the tracer from the
    same global provider at request time.
    """
    app = FastAPI()

    @app.get("/ping")
    async def ping() -> dict[str, str]:
        return {"status": "ok"}

    configure_tracing(service_name="test-service", otlp_endpoint="http://localhost:4318", app=app)

    provider = trace.get_tracer_provider()
    assert isinstance(provider, TracerProvider)
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    async def _call() -> int:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/ping")
        return response.status_code

    status_code = asyncio.run(_call())

    assert status_code == 200
    spans = exporter.get_finished_spans()
    assert any("ping" in span.name for span in spans)
