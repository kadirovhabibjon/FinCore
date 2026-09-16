from __future__ import annotations

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel


class ProblemDetail(BaseModel):
    """RFC 7807 Problem Details response body.

    Every FinCore service returns errors in this shape (Section 20 of the
    spec), so a client never has to special-case error parsing per
    service.
    """

    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


class DomainError(Exception):
    """Base class for a service's domain-level errors.

    Subclass per error case and set `status_code` and `title` as class
    attributes, e.g.:

        class EmailAlreadyRegisteredError(DomainError):
            status_code = status.HTTP_409_CONFLICT
            title = "Email Already Registered"

    Raising a DomainError anywhere in a request produces a well-formed
    RFC 7807 response automatically once `register_error_handlers(app)`
    has been called — no per-route try/except needed.
    """

    status_code: int = status.HTTP_400_BAD_REQUEST
    title: str = "Bad Request"

    def __init__(self, detail: str | None = None) -> None:
        super().__init__(detail or self.title)
        self.detail = detail


def _problem_response(
    status_code: int, title: str, detail: str | None, instance: str | None
) -> JSONResponse:
    problem = ProblemDetail(
        title=title, status=status_code, detail=detail, instance=instance
    )
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(exclude_none=True),
        media_type="application/problem+json",
    )


def register_error_handlers(app: FastAPI) -> None:
    """Wire up RFC 7807 responses for domain errors and request validation.

    Call this once, right after constructing the FastAPI app.
    """

    @app.exception_handler(DomainError)
    async def _handle_domain_error(request: Request, exc: DomainError) -> JSONResponse:
        return _problem_response(
            exc.status_code, exc.title, exc.detail, str(request.url)
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        return _problem_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Validation Error",
            detail,
            str(request.url),
        )
