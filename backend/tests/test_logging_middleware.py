"""Tests for HTTP request and response logging middleware."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from app.core.logging_middleware import HttpLoggingMiddleware


def _build_app() -> FastAPI:
    """Create a minimal FastAPI app using the HTTP logging middleware."""

    app = FastAPI()
    app.add_middleware(HttpLoggingMiddleware, body_max_chars=1000, body_enabled=True)

    @app.post("/echo")
    async def echo(request: Request) -> JSONResponse:
        body = await request.json()
        return JSONResponse({"received": body, "token": "response-secret"})

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(iter([b"hello"]), media_type="text/plain")

    return app


def _parse_http_logs(caplog) -> list[dict]:
    """Parse JSON payloads emitted by the HTTP logging middleware."""

    messages: list[dict] = []
    for record in caplog.records:
        if record.name != "app.http":
            continue
        try:
            messages.append(json.loads(record.getMessage()))
        except json.JSONDecodeError:
            payload = getattr(record, "payload", None)
            if isinstance(payload, dict):
                messages.append(payload)
    return messages


def test_http_logging_middleware_logs_sanitized_bodies(caplog) -> None:
    """Middleware logs request and response bodies without breaking endpoint reads."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.post("/echo", json={"password": "pw", "name": "alice"})

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json()["received"] == {"password": "pw", "name": "alice"}

    messages = _parse_http_logs(caplog)

    assert any(message["event"] == "http.request" for message in messages)
    assert any(message["event"] == "http.response" for message in messages)
    request_log = next(message for message in messages if message["event"] == "http.request")
    response_log = next(message for message in messages if message["event"] == "http.response")
    assert request_log["request_body"]["password"] == "[REDACTED]"
    assert response_log["response_body"]["token"] == "[REDACTED]"


def test_http_logging_middleware_does_not_consume_streams(caplog) -> None:
    """Streaming responses are returned intact and logged as summaries."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.get("/stream")

    assert response.status_code == 200
    assert response.text == "hello"
