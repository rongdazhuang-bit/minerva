"""Tests for reasoning token extraction helpers."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.agent.infrastructure.openai_usage import (
    extract_usage_document,
    reasoning_tokens_from_usage_document,
)
from app.agent.infrastructure.reasoning_collector import (
    ReasoningCollector,
    reasoning_tokens_from_raw,
)


def test_reasoning_tokens_from_usage_document_reads_details() -> None:
    """Layered usage documents expose reasoning counts under ``details``."""

    doc = {
        "prompt_tokens": 10,
        "completion_tokens": 8,
        "total_tokens": 18,
        "details": {"reasoning_tokens": 5},
    }
    assert reasoning_tokens_from_usage_document(doc) == 5


def test_reasoning_tokens_from_raw_reads_completion_details() -> None:
    """Per-call extraction must not drop ``completion_tokens_details``."""

    raw = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "completion_tokens_details": {"reasoning_tokens": 3},
    }
    assert reasoning_tokens_from_raw(raw) == 3


@pytest.mark.asyncio
async def test_mark_all_done_falls_back_to_run_usage() -> None:
    """Final reasoning total can come from run usage when segment counts are zero."""

    emitted: list[int] = []

    async def emit_sse(blob: bytes) -> None:
        import orjson

        payload = orjson.loads(blob.removeprefix(b"data: ").rstrip())
        if payload["type"] == "llm.reasoning.done":
            emitted.append(int(payload["payload"]["reasoning_tokens"]))

    collector = ReasoningCollector("run", "sess", emit_sse, thinking_enabled=True)
    await collector.append_delta("planner", "think")
    await collector.finalize_segment("planner", reasoning_tokens=0)
    await collector.mark_all_done(
        fallback_usage={
            "prompt_tokens": 10,
            "completion_tokens": 8,
            "total_tokens": 18,
            "details": {"reasoning_tokens": 12},
        },
    )

    assert emitted == [12]
    reasoning = collector.build_message_reasoning()
    assert reasoning is not None
    assert reasoning["reasoning_tokens"] == 12
