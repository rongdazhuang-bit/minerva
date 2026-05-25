"""Stream sub-agent runs and map events to SSE v2."""

from __future__ import annotations

import uuid

from langgraph.graph.state import CompiledStateGraph

from app.agent.domain.plan import PlanStep
from app.agent.graphs.deps import GraphDeps
from app.agent.infrastructure.chat_history import messages_with_user_input
from app.agent.infrastructure.event_mapper import map_langchain_stream_event


def extract_last_ai_text(messages: list) -> str:
    """Pull the last assistant text from sub-agent message list."""

    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("ai", "assistant"):
            content = getattr(msg, "content", "") or ""
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""


async def run_subagent_with_stream(
    deps: GraphDeps,
    subagent: CompiledStateGraph,
    *,
    step: PlanStep,
    recursion_limit: int,
    parent_node_id: uuid.UUID,
) -> str:
    """Run one sub-agent with ``astream_events`` and forward tool/LLM deltas to SSE."""

    config_sub = {"recursion_limit": recursion_limit}
    history = deps.conversation_messages or []
    inputs = {"messages": messages_with_user_input(history, step.goal)}
    output = ""
    async for event in subagent.astream_events(inputs, config=config_sub, version="v2"):
        if event.get("event") == "on_chat_model_end":
            data = event.get("data") or {}
            await deps.record_llm_call_to_db(
                data.get("output"),
                parent_node_id=parent_node_id,
                phase="subagent",
                step_id=step.id,
                skill_id=step.skill_id,
            )
        if deps.emit_sse:
            line = map_langchain_stream_event(
                event,
                run_id=deps.run_id,
                session_id=deps.session_id,
                step_id=step.id,
                skill_id=step.skill_id,
            )
            if line:
                await deps.emit_sse(line)
        if event.get("event") == "on_chain_end":
            data = event.get("data") or {}
            out = data.get("output")
            if isinstance(out, dict) and out.get("messages"):
                output = extract_last_ai_text(out["messages"])
    if not output:
        result = await subagent.ainvoke(inputs, config=config_sub)
        messages = result.get("messages", [])
        for msg in reversed(messages):
            role = getattr(msg, "type", None) or getattr(msg, "role", None)
            if role in ("ai", "assistant"):
                await deps.record_llm_call_to_db(
                    msg,
                    parent_node_id=parent_node_id,
                    phase="subagent",
                    step_id=step.id,
                    skill_id=step.skill_id,
                )
                break
        output = extract_last_ai_text(messages)
    return output
