"""Shared httpx helpers, logging, and upstream error mapping for LLM strategies."""

from __future__ import annotations

import logging
from typing import Any

import orjson
from httpx import AsyncClient, HTTPStatusError, RequestError, Timeout, TimeoutException

from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)

_LOG_JSON_MAX_CHARS = 100_000


def normalize_endpoint_url(url: str) -> str:
    """Normalize configured provider URL without path rewriting."""

    return url.rstrip("/")


normalize_openai_base_url = normalize_endpoint_url


def json_for_log(data: Any) -> str:
    """Serialize for logging; truncate very large payloads."""

    raw = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode()
    if len(raw) > _LOG_JSON_MAX_CHARS:
        return raw[:_LOG_JSON_MAX_CHARS] + f"... [truncated, original_length={len(raw)} chars]"
    return raw


def text_for_log(text: str) -> str:
    """Truncate huge plaintext log payloads."""

    if len(text) > _LOG_JSON_MAX_CHARS:
        return text[:_LOG_JSON_MAX_CHARS] + f"... [truncated, original_length={len(text)}]"
    return text


def request_headers(api_key: str) -> dict[str, str]:
    """Build OpenAI-compatible HTTP headers."""

    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def client_timeout() -> Timeout:
    """Construct httpx.Timeout from AI-related settings."""

    return Timeout(
        connect=settings.ai_http_connect_timeout,
        read=settings.ai_http_read_timeout,
        write=settings.ai_http_read_timeout,
        pool=settings.ai_http_connect_timeout,
    )


def log_upstream_http_error(*, url: str, exc: HTTPStatusError, method: str) -> None:
    """Emit WARNING logs containing sanitized upstream HTTP bodies."""

    body = ""
    if exc.response is not None:
        try:
            body = exc.response.text
        except Exception:  # noqa: BLE001
            body = repr(exc)
    log.warning(
        "ai upstream error method=%s url=%s status=%s response=%s",
        method,
        url,
        exc.response.status_code if exc.response is not None else "unknown",
        text_for_log(body) if body else "",
    )


def map_upstream_error(exc: BaseException) -> AppError:
    """Normalize upstream transport failures into stable AppError codes."""

    if isinstance(exc, HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return AppError("ai.upstream.unauthorized", "Upstream rejected the API key.", 502)
        if code == 429:
            return AppError("ai.upstream.rate_limited", "Upstream rate limited the request.", 429)
        if code == 503:
            return AppError("ai.upstream.unavailable", "Upstream temporarily unavailable.", 503)
        if code >= 500:
            return AppError("ai.upstream.error", f"Upstream returned HTTP {code}.", 502)
        return AppError("ai.upstream.bad_request", f"Upstream returned HTTP {code}.", 400)
    if isinstance(exc, TimeoutException):
        return AppError("ai.upstream.timeout", "Upstream request timed out.", 504)
    if isinstance(exc, RequestError):
        return AppError("ai.upstream.connection", "Could not connect to upstream.", 502)
    return AppError("ai.error", str(exc) or "Unknown AI error", 500)


async def post_json(
    *,
    url: str,
    api_key: str,
    body: dict[str, Any],
    log_label: str,
) -> dict[str, Any]:
    """POST JSON to upstream and return parsed response dict."""

    target = normalize_endpoint_url(url)
    log.info("ai %s request url=%s body=%s", log_label, target, json_for_log(body))
    try:
        async with AsyncClient(timeout=client_timeout()) as client:
            resp = await client.post(target, json=body, headers=request_headers(api_key))
            resp.raise_for_status()
            out = resp.json()
            log.info("ai %s response url=%s body=%s", log_label, target, json_for_log(out))
            return out
    except HTTPStatusError as e:
        log_upstream_http_error(url=target, exc=e, method=log_label)
        raise map_upstream_error(e) from None
    except (TimeoutException, RequestError) as e:
        log.warning("ai %s transport error url=%s error=%s", log_label, target, e)
        raise map_upstream_error(e) from None
    except AppError:
        raise
    except Exception as e:
        log.exception("ai %s unexpected error url=%s", log_label, target)
        raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e
