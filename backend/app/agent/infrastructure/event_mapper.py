"""Map LangChain / LangGraph stream events to Agent SSE v2 lines."""

from __future__ import annotations

import uuid
from typing import Any

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event


def map_langchain_stream_event(
    event: dict[str, Any],
    *,
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    step_id: str | None = None,
    capability: str | None = None,
) -> bytes | None:
    """Convert one ``astream_events`` v2 dict to an SSE line, or None if skipped."""

    kind = event.get("event")
    if kind == "on_chat_model_stream":
        data = event.get("data", {})
        chunk = data.get("chunk")
        if chunk is None:
            return None
        content = getattr(chunk, "content", None)
        reasoning = getattr(chunk, "additional_kwargs", {}) or {}
        reasoning_text = reasoning.get("reasoning_content") or reasoning.get("reasoning")
        if reasoning_text:
            return build_sse_event(
                event_type=AgentSseEventType.llm_delta,
                run_id=run_id,
                session_id=session_id,
                payload={
                    "channel": "reasoning",
                    "text": str(reasoning_text),
                    "step_id": step_id,
                    "capability": capability,
                },
            )
        if content:
            return build_sse_event(
                event_type=AgentSseEventType.llm_delta,
                run_id=run_id,
                session_id=session_id,
                payload={
                    "channel": "assistant",
                    "text": str(content),
                    "step_id": step_id,
                    "capability": capability,
                },
            )
    if kind == "on_tool_start":
        return build_sse_event(
            event_type=AgentSseEventType.tool_started,
            run_id=run_id,
            session_id=session_id,
            payload={
                "tool_call_id": event.get("run_id", ""),
                "name": event.get("name", ""),
                "arguments_preview": "",
                "step_id": step_id,
                "capability": capability,
            },
        )
    if kind == "on_tool_end":
        output = event.get("data", {}).get("output")
        preview = str(output)[:240] if output is not None else ""
        return build_sse_event(
            event_type=AgentSseEventType.tool_finished,
            run_id=run_id,
            session_id=session_id,
            payload={
                "tool_call_id": event.get("run_id", ""),
                "name": event.get("name", ""),
                "result_preview": preview,
                "status": "success",
                "step_id": step_id,
                "capability": capability,
            },
        )
    return None
