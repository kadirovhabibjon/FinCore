from fastapi import FastAPI, status
from starlette.testclient import TestClient

from fincore_common.errors import DomainError, register_error_handlers


class _EmailTakenError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Email Already Registered"


def _build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    async def boom():
        raise _EmailTakenError(detail="a@example.com is already registered")

    @app.post("/validated")
    async def validated(payload: dict[str, int]):
        return payload

    return app


def test_domain_error_is_rendered_as_rfc7807_problem_json() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.get("/boom")

    assert response.status_code == 409
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert body["title"] == "Email Already Registered"
    assert body["status"] == 409
    assert body["detail"] == "a@example.com is already registered"
    assert body["instance"].endswith("/boom")


def test_validation_error_is_rendered_as_rfc7807_problem_json() -> None:
    client = TestClient(_build_app(), raise_server_exceptions=False)

    response = client.post("/validated", json={"not": "an int"})

    assert response.status_code == 422
    body = response.json()
    assert body["title"] == "Validation Error"
    assert body["status"] == 422
    assert "detail" in body
