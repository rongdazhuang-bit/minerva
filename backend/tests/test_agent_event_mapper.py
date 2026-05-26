"""Tests for LangChain stream event → SSE v2 mapping."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

from app.agent.infrastructure.event_mapper import map_langchain_stream_event


def test_map_reasoning_delta_includes_phase() -> None:
    """Reasoning chunks should carry phase metadata for the UI."""

    chunk = SimpleNamespace(content="", additional_kwargs={"reasoning_content": "r1"})
    event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}}
    line = map_langchain_stream_event(
        event,
        run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        phase="subagent",
        step_id="s1",
        skill_id="file",
    )
    assert line is not None
    assert b'"channel":"reasoning"' in line
    assert b'"phase":"subagent"' in line
    assert b'"step_id":"s1"' in line


def test_map_reasoning_skipped_when_emit_reasoning_false() -> None:
    """Collector-owned reasoning should not duplicate SSE from the mapper."""

    chunk = SimpleNamespace(content="", additional_kwargs={"reasoning_content": "r1"})
    event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}}
    line = map_langchain_stream_event(
        event,
        run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        phase="subagent",
        emit_reasoning=False,
    )
    assert line is None
