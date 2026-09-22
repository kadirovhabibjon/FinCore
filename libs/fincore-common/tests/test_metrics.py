from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from fincore_common.metrics import HTTP_REQUESTS_TOTAL, configure_metrics


def _app() -> FastAPI:
    app = FastAPI()

    @app.get("/ping/{item_id}")
    async def ping(item_id: str) -> dict[str, str]:
        return {"item_id": item_id}

    configure_metrics(app, service_name="test-service")
    return app


async def test_metrics_endpoint_serves_prometheus_text_format() -> None:
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "text/plain" in response.headers["content-type"]
    assert "fincore_http_requests_total" in response.text


async def test_a_request_increments_the_counter_labeled_by_path_template_not_raw_path() -> None:
    """The label must be the route's path *template*
    (`/ping/{item_id}`), not the literal request path — otherwise every
    distinct id ever requested becomes its own time series.
    """
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/ping/abc")
        await client.get("/ping/xyz")

    value = HTTP_REQUESTS_TOTAL.labels(
        service="test-service", method="GET", path="/ping/{item_id}", status_code="200"
    )._value.get()
    assert value >= 2


async def test_the_metrics_endpoint_itself_is_not_counted() -> None:
    app = _app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/metrics")

    assert 'path="/metrics"' not in response.text
