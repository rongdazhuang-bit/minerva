"""Serialize OpenAI-compatible SSE ``data:`` lines for agent runs."""

from __future__ import annotations

from typing import Any

import orjson

from app.agent.domain.openai_chunk import OpenAiChatCompletionChunk, build_minerva_chunk
from app.agent.domain.sse_minerva import MinervaChunkExtension

SSE_DONE_LINE = b"data: [DONE]\n\n"


def sse_data_line(payload: dict[str, Any]) -> bytes:
    """Format one ``data:`` SSE frame from a JSON object."""

    return b"data: " + orjson.dumps(payload) + b"\n\n"


def emit_upstream_chunk(chunk: dict[str, Any]) -> bytes:
    """Passthrough an upstream completion chunk without reshaping fields."""

    return sse_data_line(chunk)


def emit_minerva_event(
    ext: MinervaChunkExtension,
    *,
    model: str,
    chunk_id: str | None = None,
) -> bytes:
    """Emit a synthetic OpenAI chunk carrying only the ``minerva`` extension."""

    envelope = build_minerva_chunk(ext, model=model, chunk_id=chunk_id)
    return sse_data_line(envelope.to_sse_dict())


def emit_openai_error(*, message: str, code: str, error_type: str = "invalid_request_error") -> bytes:
    """Emit an OpenAI-style error object on the SSE stream."""

    return sse_data_line(
        {
            "error": {
                "message": message,
                "type": error_type,
                "code": code,
            }
        }
    )
