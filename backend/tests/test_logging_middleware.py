"""Tests for HTTP request and response logging middleware."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient
from _pytest.logging import LogCaptureFixture

from app.core.logging_json import JsonLogFormatter
from app.core.logging_middleware import HttpLoggingMiddleware


def _http_log_messages(caplog: LogCaptureFixture) -> list[dict[str, Any]]:
    """Return formatted JSON payloads emitted by the HTTP logger."""

    formatter = JsonLogFormatter()
    return [
        json.loads(formatter.format(record))
        for record in caplog.records
        if record.name == "app.http"
    ]


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
        return StreamingResponse(iter([b"hello"]), media_type="text/event-stream")

    @app.get("/download")
    async def download() -> StreamingResponse:
        return StreamingResponse(iter([b"x" * 10000]), media_type="application/octet-stream")

    @app.post("/runs")
    async def runs(body: dict) -> StreamingResponse:
        async def event_stream():
            yield b"data: ok\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    return app


def test_http_logging_middleware_logs_sanitized_bodies(caplog: LogCaptureFixture) -> None:
    """Middleware logs request and response bodies without breaking endpoint reads."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.post("/echo", json={"password": "pw", "name": "alice"})

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json()["received"] == {"password": "pw", "name": "alice"}

    http_records = [record for record in caplog.records if record.name == "app.http"]
    assert all(record.getMessage() in {"http.request", "http.response"} for record in http_records)

    messages = _http_log_messages(caplog)
    assert any(message["event"] == "http.request" for message in messages)
    assert any(message["event"] == "http.response" for message in messages)
    request_log = next(message for message in messages if message["event"] == "http.request")
    response_log = next(message for message in messages if message["event"] == "http.response")
    assert request_log["request_body"]["password"] == "[REDACTED]"
    assert response_log["response_body"]["token"] == "[REDACTED]"


def test_http_logging_middleware_does_not_consume_streams(caplog: LogCaptureFixture) -> None:
    """Streaming responses are returned intact and logged as summaries."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.get("/stream")

    assert response.status_code == 200
    assert response.text == "hello"

    response_log = next(
        message for message in _http_log_messages(caplog) if message["event"] == "http.response"
    )
    assert response_log["response_body"]["streaming"] is True


def test_http_logging_middleware_post_sse_does_not_hang(caplog: LogCaptureFixture) -> None:
    """POST + SSE must not deadlock when disconnect listeners read receive again."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.post("/runs", json={"user_message": "hello", "model_id": "test"})

    assert response.status_code == 200
    assert "ok" in response.text


def test_http_logging_middleware_skips_octet_stream_body_buffer(caplog: LogCaptureFixture) -> None:
    """Binary downloads are not buffered into response logs."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.get("/download")

    assert response.status_code == 200
    assert len(response.content) == 10000

    response_log = next(
        message for message in _http_log_messages(caplog) if message["event"] == "http.response"
    )
    assert response_log["response_body"] == {
        "streaming": True,
        "content_type": "application/octet-stream",
    }
