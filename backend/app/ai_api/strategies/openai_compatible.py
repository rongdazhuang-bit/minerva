"""OpenAI-compatible ``AsyncOpenAI`` integration with structured logging."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import orjson
from httpx import Timeout
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI

from app.ai_api.domain.models import ChatCallParams
from app.config import settings
from app.exceptions import AppError

log = logging.getLogger(__name__)

# Endpoint suffix appended to user-provided base URLs for chat completions.
_CHAT_COMPLETIONS_PATH = "/chat/completions"
_LOG_JSON_MAX_CHARS = 100_000


def _chat_completions_url(base_url: str) -> str:
    """Append chat completions suffix with normalized slashes."""

    return base_url.rstrip("/") + _CHAT_COMPLETIONS_PATH


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
        "ai.chat.completions upstream error method=%s url=%s status=%s response=%s",
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


class OpenAICompatibleStrategy:
    """Concrete strategy issuing REST chat completions against OpenAI-compatible APIs."""

    async def complete(self, params: ChatCallParams) -> dict[str, Any]:
        """Perform blocking completion with structured logging."""

        base_url = params.base_url.rstrip("/")
        url = _chat_completions_url(base_url)
        kwargs = _completion_kwargs(params, stream=False)
        log.info(
            "ai.chat.completions request method=complete url=%s body=%s",
            url,
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
                    "ai.chat.completions response method=complete url=%s body=%s",
                    url,
                    _json_for_log(out),
                )
                return out
        except APIStatusError as e:
            _log_upstream_http_error(url=url, exc=e, method="complete")
            raise _map_openai_error(e) from None
        except (APITimeoutError, APIConnectionError) as e:
            log.warning(
                "ai.chat.completions upstream transport error method=complete url=%s error=%s",
                url,
                e,
            )
            raise _map_openai_error(e) from None
        except AppError:
            raise
        except Exception as e:
            log.exception("ai complete unexpected error model=%s", params.model)
            raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e

    async def stream(self, params: ChatCallParams) -> AsyncIterator[dict[str, Any]]:
        """Yield streamed completion chunks while summarizing traffic for logs."""

        base_url = params.base_url.rstrip("/")
        url = _chat_completions_url(base_url)
        kwargs = _completion_kwargs(params, stream=True)
        log.info(
            "ai.chat.completions request method=stream url=%s body=%s",
            url,
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
                    "ai.chat.completions response method=stream url=%s body=%s",
                    url,
                    _json_for_log(summary),
                )
        except APIStatusError as e:
            _log_upstream_http_error(url=url, exc=e, method="stream")
            raise _map_openai_error(e) from None
        except (APITimeoutError, APIConnectionError) as e:
            log.warning(
                "ai.chat.completions upstream transport error method=stream url=%s error=%s",
                url,
                e,
            )
            raise _map_openai_error(e) from None
        except AppError:
            raise
        except Exception as e:
            log.exception("ai stream unexpected error model=%s", params.model)
            raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e
