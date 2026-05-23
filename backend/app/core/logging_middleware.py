"""HTTP middleware that logs sanitized request and response payloads."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.core.logging_context import use_logging_context
from app.core.logging_redaction import redact_for_log

_HTTP_LOGGER = logging.getLogger("app.http")
_STREAMING_TYPES = ("text/event-stream",)


def _parse_body(raw: bytes, headers: Headers, *, max_chars: int) -> Any:
    """Parse a request or response body into a safe log value."""

    content_type = headers.get("content-type", "")
    if not raw:
        return None
    if "multipart/form-data" in content_type:
        return {"multipart": True, "length": len(raw)}
    if "application/json" in content_type:
        try:
            return redact_for_log(json.loads(raw.decode("utf-8")), max_chars=max_chars)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"unparseable_json": True, "length": len(raw)}
    if content_type.startswith("text/"):
        return redact_for_log(raw.decode("utf-8", errors="replace"), max_chars=max_chars)
    return {"binary": True, "length": len(raw), "content_type": content_type}


def _safe_headers(headers: Headers, *, max_chars: int) -> dict[str, Any]:
    """Return sanitized request or response headers."""

    return redact_for_log(dict(headers.items()), max_chars=max_chars)


class HttpLoggingMiddleware:
    """Log HTTP request and response metadata plus sanitized payloads."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        body_enabled: bool | None = None,
        body_max_chars: int | None = None,
    ) -> None:
        """Initialize middleware with optional test overrides."""

        self.app = app
        self.body_enabled = settings.log_body_enabled if body_enabled is None else body_enabled
        self.body_max_chars = body_max_chars or settings.log_body_max_chars

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI request and emit request/response logs."""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        request_headers = Headers(scope=scope)
        content_length = request_headers.get("content-length", "").strip()
        has_request_body = scope["method"] in {"POST", "PUT", "PATCH", "DELETE"} or bool(content_length)
        raw_body = await request.body() if has_request_body else b""

        downstream_receive: Receive = receive
        if has_request_body:

            async def replay_receive() -> Message:
                """Replay the already-read request body for downstream handlers."""

                return {"type": "http.request", "body": raw_body, "more_body": False}

            downstream_receive = replay_receive

        with use_logging_context(request_id=request_id):
            if self.body_enabled:
                request_payload = {
                    "event": "http.request",
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "query": redact_for_log(dict(request.query_params), max_chars=self.body_max_chars),
                    "client_ip": request.client.host if request.client else None,
                    "headers": _safe_headers(request_headers, max_chars=self.body_max_chars),
                    "content_type": request_headers.get("content-type"),
                    "request_body": _parse_body(raw_body, request_headers, max_chars=self.body_max_chars),
                }
                _HTTP_LOGGER.info(
                    json.dumps(request_payload, ensure_ascii=False),
                    extra={"event": "http.request", "payload": request_payload},
                )
            await self._send_with_response_logging(
                scope,
                downstream_receive,
                send,
                request_id=request_id,
                started=started,
            )

    async def _send_with_response_logging(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        request_id: str,
        started: float,
    ) -> None:
        """Wrap ASGI send to capture non-streaming response bodies."""

        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        body_parts: list[bytes] = []
        streaming = False

        async def wrapped_send(message: Message) -> None:
            """Capture response metadata and forward each ASGI message."""

            nonlocal status_code, response_headers, streaming
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": response_headers}
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if message.get("more_body", False):
                    streaming = True
                elif body:
                    body_parts.append(body)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            headers = Headers(raw=response_headers)
            content_type = headers.get("content-type", "")
            is_stream = streaming or content_type.startswith(_STREAMING_TYPES)
            if is_stream:
                response_body: Any = {"streaming": True, "content_type": content_type}
            elif self.body_enabled:
                response_body = _parse_body(
                    b"".join(body_parts),
                    headers,
                    max_chars=self.body_max_chars,
                )
            else:
                response_body = None
            response_payload = {
                "event": "http.response",
                "request_id": request_id,
                "method": scope["method"],
                "path": scope["path"],
                "status_code": status_code,
                "duration_ms": duration_ms,
                "content_type": content_type,
                "response_body": response_body,
            }
            _HTTP_LOGGER.info(
                json.dumps(response_payload, ensure_ascii=False),
                extra={
                    "event": "http.response",
                    "status_code": status_code,
                    "payload": response_payload,
                },
            )
