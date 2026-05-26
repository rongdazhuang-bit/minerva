"""Tests for ReasoningCollector SSE payloads and persistence helpers."""

from __future__ import annotations

import uuid
from typing import Any

import orjson
import pytest

from app.agent.infrastructure.reasoning_collector import ReasoningCollector


def _loads_sse_data_line(line: bytes) -> dict[str, Any]:
    """Decode ``data:`` JSON body from ``build_sse_event`` output."""

    assert line.startswith(b"data: ")
    return orjson.loads(line.removeprefix(b"data: ").rstrip())


@pytest.mark.asyncio
async def test_append_delta_finalize_segment_sse_and_snapshot() -> None:
    """Deltas accumulate per segment keys and emits complete reasoning lifecycle SSE."""

    emitted: list[dict[str, Any]] = []

    async def emit_sse(blob: bytes) -> None:
        emitted.append(_loads_sse_data_line(blob))

    rid = uuid.uuid4()
    sid = uuid.uuid4()
    collector = ReasoningCollector(rid, sid, emit_sse, thinking_enabled=True)

    await collector.append_delta("planner", "p1-", step_id=None, skill_id=None)
    await collector.append_delta("planner", "tail", step_id=None, skill_id=None)
    await collector.finalize_segment("planner", reasoning_tokens=5)
    await collector.append_delta(
        "subagent",
        "x",
        step_id="s1",
        skill_id="file",
    )
    await collector.finalize_segment("subagent", reasoning_tokens=3, step_id="s1", skill_id="file")
    await collector.mark_all_done()

    assert len(emitted) == 6
    assert emitted[0]["type"] == "llm.delta"
    assert emitted[0]["payload"] == {
        "channel": "reasoning",
        "phase": "planner",
        "step_id": None,
        "skill_id": None,
        "text": "p1-",
    }
    assert emitted[1]["type"] == "llm.delta"
    assert emitted[1]["payload"]["text"] == "tail"
    assert emitted[2]["type"] == "llm.reasoning.segment_done"
    assert emitted[2]["payload"]["reasoning_tokens"] == 5
    assert emitted[4]["type"] == "llm.reasoning.segment_done"
    assert emitted[5]["type"] == "llm.reasoning.done"
    assert emitted[5]["payload"]["reasoning_tokens"] == 8

    reasoning = collector.build_message_reasoning()
    assert reasoning is not None
    assert reasoning["reasoning_tokens"] == 8
    assert reasoning["segments"][0]["text"] == "p1-tail"

    merged = collector.build_message_reasoning_text()
    assert merged == "[Planner]\np1-tail\n\n[file · s1]\nx"


@pytest.mark.asyncio
async def test_thinking_disabled_is_noop() -> None:
    """When thinking mode is off, collector skips SSE and persistence builders yield None."""

    saw: list[bytes] = []

    async def emit_sse(blob: bytes) -> None:
        saw.append(blob)

    rid = uuid.uuid4()
    collector = ReasoningCollector(rid, None, emit_sse, thinking_enabled=False)

    await collector.append_delta("planner", "nope")
    await collector.finalize_segment("planner", reasoning_tokens=10)
    await collector.mark_all_done()

    assert saw == []
    assert collector.build_message_reasoning() is None
    assert collector.build_message_reasoning_text() is None
