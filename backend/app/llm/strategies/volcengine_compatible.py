"""Volcengine Ark OpenAI-compatible ``AsyncOpenAI`` integration with structured logging."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import orjson
from httpx import Timeout
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.llm.domain.models import ChatCallParams
from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)

_LOG_JSON_MAX_CHARS = 100_000


def _client_base_url(raw: str) -> str:
    """Return ``base_url`` for ``AsyncOpenAI`` as configured (trim only).

    Ark expects ``https://ark.<region>.volces.com/api/v3``; the SDK appends
    ``/chat/completions``. Strip a trailing ``/responses`` segment when present
    (OpenAI Responses API path) so we do not call ``.../responses/chat/completions``.
    """

    url = raw.strip()
    normalized = url.rstrip("/")
    if normalized.endswith("/responses"):
        return normalized[: -len("/responses")]
    return url


def _json_for_log(data: Any) -> str:
    """Serialize for logging; truncate very large payloads to protect log sinks."""
    raw = orjson.dumps(data, option=orjson.OPT_INDENT_2 | orjson.OPT_NON_STR_KEYS).decode()
    if len(raw) > _LOG_JSON_MAX_CHARS:
        return (
            raw[:_LOG_JSON_MAX_CHARS]
            + f'... [truncated, original_length={len(raw)} chars]'
        )
    return raw


def _completion_kwargs(params: ChatCallParams, *, stream: bool) -> dict[str, Any]:
    """Translate ``ChatCallParams`` into kwargs accepted by ``chat.completions.create``."""

    kwargs: dict[str, Any] = {
        "model": params.model,
        "messages": params.messages,
        "stream": stream,
    }
    if params.temperature is not None:
        kwargs["temperature"] = params.temperature
    if params.max_tokens is not None:
        kwargs["max_tokens"] = params.max_tokens
    if params.tools is not None:
        kwargs["tools"] = params.tools
    if params.tool_choice is not None:
        kwargs["tool_choice"] = params.tool_choice
    return kwargs


def _text_for_log(text: str) -> str:
    """Truncate huge plaintext payloads intended for info logs."""

    if len(text) > _LOG_JSON_MAX_CHARS:
        return text[:_LOG_JSON_MAX_CHARS] + f"... [truncated, original_length={len(text)}]"
    return text


def _log_upstream_http_error(*, url: str, exc: APIStatusError, method: str) -> None:
    """Emit WARNING logs containing sanitized upstream HTTP bodies."""

    body = ""
    if exc.response is not None:
        try:
            body = exc.response.text
        except Exception:  # noqa: BLE001
            body = repr(exc)
    log.warning(
        "ai.volcengine.chat.completions upstream error method=%s url=%s status=%s response=%s",
        method,
        url,
        exc.status_code,
        _text_for_log(body) if body else "",
    )


def _client_timeout() -> Timeout:
    """Construct ``httpx.Timeout`` from AI-related ``settings`` fields."""

    return Timeout(
        connect=settings.ai_http_connect_timeout,
        read=settings.ai_http_read_timeout,
        write=settings.ai_http_read_timeout,
        pool=settings.ai_http_connect_timeout,
    )


def _map_openai_error(exc: BaseException) -> AppError:
    """Normalize upstream transport/SDK failures into stable ``AppError`` codes."""

    if isinstance(exc, APIStatusError):
        code = exc.status_code
        if code == 401:
            return AppError("ai.upstream.unauthorized", "Upstream rejected the API key.", 502)
        if code == 429:
            return AppError("ai.upstream.rate_limited", "Upstream rate limited the request.", 429)
        if code == 503:
            return AppError("ai.upstream.unavailable", "Upstream temporarily unavailable.", 503)
        if code >= 500:
            return AppError(
                "ai.upstream.error",
                f"Upstream returned HTTP {code}.",
                502,
            )
        return AppError(
            "ai.upstream.bad_request",
            f"Upstream returned HTTP {code}.",
            400,
        )
    if isinstance(exc, APITimeoutError):
        return AppError("ai.upstream.timeout", "Upstream request timed out.", 504)
    if isinstance(exc, APIConnectionError):
        return AppError("ai.upstream.connection", "Could not connect to upstream.", 502)
    return AppError("ai.error", str(exc) or "Unknown AI error", 500)


class VolcengineCompatibleStrategy:
    """Concrete strategy for Volcengine Ark via OpenAI-compatible chat completions API."""

    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        """Perform blocking completion with structured logging."""

        base_url = _client_base_url(params.base_url)
        kwargs = _completion_kwargs(params, stream=False)
        log.info(
            "ai.volcengine.chat.completions request method=complete base_url=%s body=%s",
            base_url,
            _json_for_log(kwargs),
        )
        try:
            async with AsyncOpenAI(
                api_key=params.api_key,
                base_url=base_url,
                timeout=_client_timeout(),
            ) as client:
                resp = await client.chat.completions.create(**kwargs)
                out = resp.model_dump(mode="json")
                log.info(
                    "ai.volcengine.chat.completions response method=complete base_url=%s body=%s",
                    base_url,
                    _json_for_log(out),
                )
                return out
        except APIStatusError as e:
            _log_upstream_http_error(url=base_url, exc=e, method="complete")
            raise _map_openai_error(e) from None
        except (APITimeoutError, APIConnectionError) as e:
            log.warning(
                "ai.volcengine.chat.completions upstream transport error method=complete base_url=%s error=%s",
                base_url,
                e,
            )
            raise _map_openai_error(e) from None
        except AppError:
            raise
        except Exception as e:
            log.exception("ai volcengine complete unexpected error model=%s", params.model)
            raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e

    async def stream(self, params: ChatCallParams) -> AsyncIterator[dict[str, Any]]:
        """Yield streamed completion chunks while summarizing traffic for logs."""

        base_url = _client_base_url(params.base_url)
        kwargs = _completion_kwargs(params, stream=True)
        log.info(
            "ai.volcengine.chat.completions request method=stream base_url=%s body=%s",
            base_url,
            _json_for_log(kwargs),
        )
        try:
            async with AsyncOpenAI(
                api_key=params.api_key,
                base_url=base_url,
                timeout=_client_timeout(),
            ) as client:
                upstream = await client.chat.completions.create(**kwargs)
                first_chunk: dict[str, Any] | None = None
                last_chunk: dict[str, Any] | None = None
                chunk_count = 0
                async for chunk in upstream:
                    data = chunk.model_dump(mode="json")
                    chunk_count += 1
                    if first_chunk is None:
                        first_chunk = data
                    last_chunk = data
                    yield data
                summary: dict[str, Any] = {
                    "chunk_count": chunk_count,
                    "first_chunk": first_chunk,
                    "last_chunk": last_chunk,
                }
                log.info(
                    "ai.volcengine.chat.completions response method=stream base_url=%s body=%s",
                    base_url,
                    _json_for_log(summary),
                )
        except APIStatusError as e:
            _log_upstream_http_error(url=base_url, exc=e, method="stream")
            raise _map_openai_error(e) from None
        except (APITimeoutError, APIConnectionError) as e:
            log.warning(
                "ai.volcengine.chat.completions upstream transport error method=stream base_url=%s error=%s",
                base_url,
                e,
            )
            raise _map_openai_error(e) from None
        except AppError:
            raise
        except Exception as e:
            log.exception("ai volcengine stream unexpected error model=%s", params.model)
            raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e
