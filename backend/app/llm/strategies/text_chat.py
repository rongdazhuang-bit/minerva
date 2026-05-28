"""OpenAI Chat Completions strategy for text and translate models."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from typing import Any

import orjson
from httpx import AsyncClient, HTTPStatusError, RequestError, TimeoutException

from app.exceptions import AppError
from app.llm.domain.models import TextChatCallParams, TextChatResult
from app.llm.domain.resolved_model import ResolvedModel
from app.llm.strategies.http_common import (
    client_timeout,
    json_for_log,
    log_upstream_http_error,
    map_upstream_error,
    normalize_endpoint_url,
    post_json,
    request_headers,
)

log = logging.getLogger(__name__)


def _chat_body(resolved: ResolvedModel, params: TextChatCallParams, *, stream: bool) -> dict[str, Any]:
    """Build OpenAI Chat Completions request body."""

    body: dict[str, Any] = {
        "model": resolved.model_name,
        "messages": params.messages,
        "stream": stream,
    }
    optional_fields: list[tuple[str, Any]] = [
        ("temperature", params.temperature),
        ("max_tokens", params.max_tokens),
        ("top_p", params.top_p),
        ("n", params.n),
        ("stop", params.stop),
        ("presence_penalty", params.presence_penalty),
        ("frequency_penalty", params.frequency_penalty),
        ("tools", params.tools),
        ("tool_choice", params.tool_choice),
    ]
    for key, value in optional_fields:
        if value is not None:
            body[key] = value
    return body


def _parse_chat_result(raw: dict[str, Any]) -> TextChatResult:
    """Map upstream JSON into TextChatResult."""

    return TextChatResult(
        id=raw.get("id"),
        model=raw.get("model"),
        usage=raw.get("usage"),
        choices=list(raw.get("choices") or []),
        raw=raw,
    )


class TextChatStrategy:
    """Concrete strategy for OpenAI-compatible chat completions."""

    async def complete(self, resolved: ResolvedModel, params: TextChatCallParams) -> TextChatResult:
        """Perform blocking chat completion."""

        body = _chat_body(resolved, params, stream=False)
        raw = await post_json(
            url=resolved.endpoint_url,
            api_key=resolved.api_key,
            body=body,
            log_label="chat.completions",
        )
        return _parse_chat_result(raw)

    async def stream(
        self, resolved: ResolvedModel, params: TextChatCallParams
    ) -> AsyncIterator[dict[str, Any]]:
        """Yield streamed completion chunks."""

        url = normalize_endpoint_url(resolved.endpoint_url)
        body = _chat_body(resolved, params, stream=True)
        log.info("ai chat.completions request method=stream url=%s body=%s", url, json_for_log(body))
        try:
            async with AsyncClient(timeout=client_timeout()) as client:
                first_chunk: dict[str, Any] | None = None
                last_chunk: dict[str, Any] | None = None
                chunk_count = 0
                async with client.stream(
                    "POST",
                    url,
                    json=body,
                    headers=request_headers(resolved.api_key),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        payload = line.removeprefix("data:").strip()
                        if not payload:
                            continue
                        if payload == "[DONE]":
                            break
                        data = orjson.loads(payload)
                        chunk_count += 1
                        if first_chunk is None:
                            first_chunk = data
                        last_chunk = data
                        yield data
                summary = {
                    "chunk_count": chunk_count,
                    "first_chunk": first_chunk,
                    "last_chunk": last_chunk,
                }
                log.info(
                    "ai chat.completions response method=stream url=%s body=%s",
                    url,
                    json_for_log(summary),
                )
        except HTTPStatusError as e:
            log_upstream_http_error(url=url, exc=e, method="stream")
            raise map_upstream_error(e) from None
        except (TimeoutException, RequestError) as e:
            log.warning("ai chat.completions transport error method=stream url=%s error=%s", url, e)
            raise map_upstream_error(e) from None
        except AppError:
            raise
        except Exception as e:
            log.exception("ai stream unexpected error model=%s", resolved.model_name)
            raise AppError("ai.error", "Unexpected error calling upstream.", 500) from e
