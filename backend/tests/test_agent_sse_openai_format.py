"""Tests for OpenAI-format agent SSE and minerva extension schema."""

from __future__ import annotations

import uuid
from typing import Any

import orjson
import pytest

from app.agent.domain.openai_chunk import build_minerva_chunk
from app.agent.domain.sse_minerva import (
    MinervaChunkExtension,
    MinervaErrorPayload,
    MinervaNodeSnapshot,
    MinervaNodeStatus,
    MinervaStreamEventKind,
)
from app.agent.infrastructure.sse_chunk_emitter import (
    SSE_DONE_LINE,
    emit_minerva_event,
    emit_openai_error,
    emit_upstream_chunk,
)
from app.agent.service.stream_accumulator import LlmStreamAccumulator


def test_minerva_run_started_requires_session_id() -> None:
    """``run.started`` must include ``session_id``."""

    with pytest.raises(ValueError, match="session_id"):
        MinervaChunkExtension(
            event=MinervaStreamEventKind.run_started,
            run_id=uuid.uuid4(),
            ts="2026-05-16T00:00:00Z",
        )


def test_emit_minerva_event_is_openai_chunk_shape() -> None:
    """Synthetic frames use ``object=chat.completion.chunk`` and embed ``minerva``."""

    run_id = uuid.uuid4()
    session_id = uuid.uuid4()
    ext = MinervaChunkExtension(
        event=MinervaStreamEventKind.run_started,
        run_id=run_id,
        ts="2026-05-16T00:00:00Z",
        session_id=session_id,
    )
    raw = emit_minerva_event(ext, model="gpt-4o-mini")
    assert raw.startswith(b"data: ")
    assert raw.endswith(b"\n\n")
    payload = orjson.loads(raw[6:-2])
    assert payload["object"] == "chat.completion.chunk"
    assert payload["model"] == "gpt-4o-mini"
    assert payload["minerva"]["event"] == "run.started"
    assert payload["minerva"]["v"] == 1
    assert payload["choices"][0]["delta"] == {}


def test_emit_upstream_chunk_preserves_reasoning_field() -> None:
    """Passthrough must not strip provider-specific delta keys."""

    chunk: dict[str, Any] = {
        "id": "chatcmpl-x",
        "object": "chat.completion.chunk",
        "choices": [
            {
                "index": 0,
                "delta": {"reasoning_content": "think"},
                "finish_reason": None,
            }
        ],
    }
    raw = emit_upstream_chunk(chunk)
    payload = orjson.loads(raw[6:-2])
    assert payload["choices"][0]["delta"]["reasoning_content"] == "think"


def test_emit_openai_error_shape() -> None:
    """Stream errors follow OpenAI ``error`` object layout."""

    raw = emit_openai_error(message="bad", code="agent.test")
    payload = orjson.loads(raw[6:-2])
    assert payload["error"]["message"] == "bad"
    assert payload["error"]["code"] == "agent.test"


def test_sse_done_line() -> None:
    """Terminal marker is ``[DONE]``."""

    assert SSE_DONE_LINE == b"data: [DONE]\n\n"


def test_accumulator_merges_reasoning() -> None:
    """Reasoning deltas are concatenated separately from content."""

    acc = LlmStreamAccumulator()
    acc.feed(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {"reasoning_content": "step1"},
                }
            ]
        }
    )
    acc.feed(
        {
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": "hello", "reasoning_content": " step2"},
                }
            ]
        }
    )
    assert acc.full_reasoning() == "step1 step2"
    assert acc.full_text() == "hello"
    meta = acc.build_meta_json()
    assert meta == {"reasoning": "step1 step2"}


def test_build_minerva_chunk_serializes_extension() -> None:
    """``to_sse_dict`` includes nested minerva payload."""

    run_id = uuid.uuid4()
    ext = MinervaChunkExtension(
        event=MinervaStreamEventKind.node_updated,
        run_id=run_id,
        ts="2026-05-16T00:00:00Z",
        session_id=uuid.uuid4(),
        node=MinervaNodeSnapshot(
            id=uuid.uuid4(),
            node_type="skill.pack_load",
            node_name="ocr",
            status=MinervaNodeStatus.success,
        ),
    )
    env = build_minerva_chunk(ext, model="m")
    data = env.to_sse_dict()
    assert data["minerva"]["event"] == "node.updated"
