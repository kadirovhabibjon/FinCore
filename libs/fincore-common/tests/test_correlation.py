import uuid

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from fincore_common.correlation import (
    HEADER_NAME,
    CorrelationIdMiddleware,
    get_correlation_id,
    new_correlation_id,
    reset_correlation_id,
    set_correlation_id,
)


def test_new_correlation_id_is_a_unique_uuid() -> None:
    first = new_correlation_id()
    second = new_correlation_id()

    assert first != second
    uuid.UUID(first)
    uuid.UUID(second)


def test_get_correlation_id_defaults_to_none() -> None:
    assert get_correlation_id() is None


def test_set_and_reset_round_trip() -> None:
    token = set_correlation_id("abc-123")
    assert get_correlation_id() == "abc-123"

    reset_correlation_id(token)
    assert get_correlation_id() is None


def _build_app() -> Starlette:
    async def whoami(request):
        return JSONResponse({"correlation_id": get_correlation_id()})

    app = Starlette(routes=[Route("/whoami", whoami)])
    app.add_middleware(CorrelationIdMiddleware)
    return app


def test_middleware_generates_id_when_none_provided() -> None:
    client = TestClient(_build_app())

    response = client.get("/whoami")

    header_value = response.headers[HEADER_NAME]
    uuid.UUID(header_value)  # raises if not a valid UUID
    assert response.json()["correlation_id"] == header_value


def test_middleware_reuses_incoming_header() -> None:
    client = TestClient(_build_app())

    response = client.get("/whoami", headers={HEADER_NAME: "caller-supplied-id"})

    assert response.headers[HEADER_NAME] == "caller-supplied-id"
    assert response.json()["correlation_id"] == "caller-supplied-id"


def test_middleware_does_not_leak_correlation_id_across_requests() -> None:
    client = TestClient(_build_app())

    client.get("/whoami", headers={HEADER_NAME: "first-request"})

    assert get_correlation_id() is None
