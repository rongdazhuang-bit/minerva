"""Integration tests for API logging wiring."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_exception_handlers


def test_generic_exception_handler_returns_stable_500() -> None:
    """Unhandled exceptions are normalized instead of exposing stack traces."""

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "internal.error"
    assert response.json()["message"] == "Internal server error"
