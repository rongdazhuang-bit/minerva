"""Run datetime capability by invoking the local tool directly (no LLM tool-calling)."""

from __future__ import annotations

import uuid

from app.agent.capabilities.datetime.answer import format_datetime_answer
from app.agent.capabilities.datetime.tools import get_system_datetime
from app.agent.domain.plan import PlanStep
from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps


async def run_datetime_capability(deps: GraphDeps, *, step: PlanStep) -> str:
    """Call ``get_system_datetime`` and return a formatted answer; emit tool SSE."""

    tool_call_id = str(uuid.uuid4())
    tool_name = get_system_datetime.name
    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.tool_started,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "arguments_preview": '{"timezone": "LOCAL"}',
                    "step_id": step.id,
                    "capability": step.capability,
                },
            )
        )

    raw = get_system_datetime.invoke({"timezone": "LOCAL"})
    answer = format_datetime_answer(raw, step.goal)

    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.tool_finished,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "result_preview": raw[:240],
                    "status": "success",
                    "step_id": step.id,
                    "capability": step.capability,
                },
            )
        )
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.llm_delta,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "channel": "assistant",
                    "text": answer,
                    "phase": "datetime",
                    "step_id": step.id,
                    "capability": step.capability,
                },
            )
        )
    return answer
