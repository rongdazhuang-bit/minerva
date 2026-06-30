"""Map LangChain / LangGraph stream events to Agent SSE v2 lines."""

from __future__ import annotations

import json
import uuid
from typing import TYPE_CHECKING, Any

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event

_TOOL_ARGS_PREVIEW_MAX_LEN = 240
_SQL_QUERY_INPUT_KEYS = ("querySql", "query_sql", "sql", "query")


def _format_tool_arguments_preview(inp: Any) -> str:
    """Build process-log preview for tool inputs; MCP SQL query args stay complete."""

    if inp is None:
        return ""
    if isinstance(inp, dict):
        for key in _SQL_QUERY_INPUT_KEYS:
            value = inp.get(key)
            if isinstance(value, str) and value.strip():
                try:
                    return json.dumps(inp, ensure_ascii=False)
                except (TypeError, ValueError):
                    return str(inp)
    text = str(inp)
    if len(text) <= _TOOL_ARGS_PREVIEW_MAX_LEN:
        return text
    return text[:_TOOL_ARGS_PREVIEW_MAX_LEN]

if TYPE_CHECKING:
    from app.agent.infrastructure.assistant_stream_collector import AssistantStreamCollector


def map_langchain_stream_event(
    event: dict[str, Any],
    *,
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    phase: str | None = None,
    step_id: str | None = None,
    skill_id: str | None = None,
    emit_reasoning: bool = False,
    assistant_stream: AssistantStreamCollector | None = None,
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
            if not emit_reasoning:
                return None
            payload: dict[str, Any] = {
                "channel": "reasoning",
                "text": str(reasoning_text),
                "step_id": step_id,
                "skill_id": skill_id,
            }
            if phase is not None:
                payload["phase"] = phase
            return build_sse_event(
                event_type=AgentSseEventType.llm_delta,
                run_id=run_id,
                session_id=session_id,
                payload=payload,
            )
        if content:
            text = str(content)
            if assistant_stream is not None:
                assistant_stream.append(text)
            return build_sse_event(
                event_type=AgentSseEventType.llm_delta,
                run_id=run_id,
                session_id=session_id,
                payload={
                    "channel": "assistant",
                    "text": text,
                    "step_id": step_id,
                    "skill_id": skill_id,
                },
            )
    if kind == "on_tool_start":
        data = event.get("data") or {}
        inp = data.get("input")
        args_preview = _format_tool_arguments_preview(inp)
        return build_sse_event(
            event_type=AgentSseEventType.tool_started,
            run_id=run_id,
            session_id=session_id,
            payload={
                "tool_call_id": str(event.get("run_id") or ""),
                "name": str(event.get("name") or ""),
                "arguments_preview": args_preview,
                "step_id": step_id,
                "skill_id": skill_id,
            },
        )
    if kind == "on_tool_end":
        output = event.get("data", {}).get("output")
        preview = (
            str(output).replace("\n", " ").replace("\r", " ")[:400]
            if output is not None
            else ""
        )
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
                "skill_id": skill_id,
            },
        )
    return None
