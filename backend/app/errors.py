"""HTTP exception handlers that normalize domain, validation, and rate-limit errors."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_core import to_jsonable_python

from app.core.log import get_logger
from app.core.logging_context import get_logging_context

log = get_logger(__name__)


class ErrorBody(BaseModel):
    """JSON envelope returned by API error handlers."""

    code: str
    message: str
    details: dict[str, Any] | None = None
    type: Literal["domain", "http", "validation"] = "domain"


def register_exception_handlers(app) -> None:
    """Attach FastAPI handlers for ``AppError`` and ``RequestValidationError``."""

    from fastapi.exceptions import RequestValidationError

    from app.exceptions import AppError

    @app.exception_handler(AppError)
    async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
        """Serialize ``AppError`` to ``ErrorBody`` with HTTP status from the exception."""

        log.warn(
            "application error",
            event="http.error",
            request_id=get_logging_context().get("request_id"),
            path=str(request.url.path),
            code=exc.code,
            status_code=exc.status_code,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorBody(
                code=exc.code,
                message=exc.message,
                type="domain",
                details=None,
            ).model_dump(mode="json"),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        """Return 422 with structured Pydantic validation issues."""

        validation_errors = to_jsonable_python(exc.errors())
        log.warn(
            "request validation error: {}",
            validation_errors,
            event="http.error",
            request_id=get_logging_context().get("request_id"),
            path=str(request.url.path),
            http_method=request.method,
            query_params=dict(request.query_params),
            code="request.validation",
            status_code=422,
            validation_errors=validation_errors,
        )
        return JSONResponse(
            status_code=422,
            content=ErrorBody(
                code="request.validation",
                message="Request validation failed",
                details={"errors": to_jsonable_python(exc.errors())},
                type="validation",
            ).model_dump(mode="json"),
        )

    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a stable 500 body while logging the original exception."""

        log.exception(
            "unhandled request error",
            event="http.error",
            request_id=get_logging_context().get("request_id"),
            path=str(request.url.path),
            code="internal.error",
            status_code=500,
        )
        return JSONResponse(
            status_code=500,
            content=ErrorBody(
                code="internal.error",
                message="Internal server error",
                type="http",
                details=None,
            ).model_dump(mode="json"),
        )
