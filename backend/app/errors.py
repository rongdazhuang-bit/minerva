from __future__ import annotations

from typing import Any, Literal

from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic_core import to_jsonable_python


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    type: Literal["domain", "http", "validation"] = "domain"


def register_exception_handlers(app) -> None:
    from fastapi.exceptions import RequestValidationError

    from app.exceptions import AppError

    @app.exception_handler(AppError)
    async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
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
        return JSONResponse(
            status_code=422,
            content=ErrorBody(
                code="request.validation",
                message="Request validation failed",
                details={"errors": to_jsonable_python(exc.errors())},
                type="validation",
            ).model_dump(mode="json"),
        )
