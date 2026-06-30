"""Stream sub-agent runs and map events to SSE v2."""

from __future__ import annotations

import uuid

from langgraph.graph.state import CompiledStateGraph

from app.agent.domain.plan import PlanStep
from app.agent.graphs.deps import GraphDeps
from app.agent.infrastructure.chat_history import messages_with_user_input_vision
from app.agent.infrastructure.event_mapper import map_langchain_stream_event
from app.agent.infrastructure.reasoning_collector import (
    extract_reasoning_from_langchain_chunk,
    extract_reasoning_from_langchain_message,
    reasoning_tokens_from_raw,
)


def extract_last_ai_text(messages: list) -> str:
    """Pull the last assistant text from sub-agent message list."""

    for msg in reversed(messages):
        role = getattr(msg, "type", None) or getattr(msg, "role", None)
        if role in ("ai", "assistant"):
            content = getattr(msg, "content", "") or ""
            if isinstance(content, str) and content.strip():
                return content.strip()
    return ""


async def _finalize_pending_llm_nodes_failed(
    deps: GraphDeps,
    pending: dict[str, uuid.UUID],
    *,
    step: PlanStep,
    error_message: str,
) -> None:
    """Finalize any in-flight ``llm.round`` rows left open after stream/interrupt errors."""

    for node_id in pending.values():
        await deps.finalize_llm_call_to_db(
            node_id,
            {},
            phase="subagent",
            step_id=step.id,
            skill_id=step.skill_id,
            status="failed",
            error_message=error_message,
        )
    pending.clear()


async def run_subagent_with_stream(
    deps: GraphDeps,
    subagent: CompiledStateGraph,
    *,
    step: PlanStep,
    recursion_limit: int,
    parent_node_id: uuid.UUID,
    goal_override: str | None = None,
) -> str:
    """Run one sub-agent with ``astream_events`` and forward tool/LLM deltas to SSE."""

    config_sub = {"recursion_limit": recursion_limit}
    history = deps.conversation_messages or []
    effective_goal = (goal_override or step.goal or "").strip()
    async with deps.workspace_files() as file_service:
        run_messages = await messages_with_user_input_vision(
            history,
            effective_goal,
            deps.user_attachments,
            workspace_id=deps.workspace_id,
            file_service=file_service,
            cache=deps.vision_cache,
            include_images=deps.model_supports_vision,
        )
    inputs = {"messages": run_messages}
    output = ""
    collector = deps.reasoning_collector
    collector_active = collector is not None and collector.thinking_enabled
    subagent_reasoning_tokens = 0
    pending_llm_nodes: dict[str, uuid.UUID] = {}

    try:
        async for event in subagent.astream_events(inputs, config=config_sub, version="v2"):
            if event.get("event") == "on_chat_model_start":
                run_id_key = str(event.get("run_id") or "")
                pending_llm_nodes[run_id_key] = await deps.begin_llm_call_to_db(
                    parent_node_id=parent_node_id,
                    phase="subagent",
                    step_id=step.id,
                    skill_id=step.skill_id,
                )
            if event.get("event") == "on_chat_model_stream" and collector_active:
                chunk = (event.get("data") or {}).get("chunk")
                if chunk is not None:
                    piece = extract_reasoning_from_langchain_chunk(chunk)
                    if piece:
                        await collector.append_delta(
                            "subagent",
                            piece,
                            step_id=step.id,
                            skill_id=step.skill_id,
                        )
            if event.get("event") == "on_chat_model_end":
                data = event.get("data") or {}
                llm_output = data.get("output")
                run_id_key = str(event.get("run_id") or "")
                llm_node_id = pending_llm_nodes.pop(run_id_key, None)
                round_text = extract_reasoning_from_langchain_message(llm_output)
                subagent_reasoning_tokens += reasoning_tokens_from_raw(llm_output)
                await deps.finalize_llm_call_to_db(
                    llm_node_id,
                    llm_output,
                    phase="subagent",
                    step_id=step.id,
                    skill_id=step.skill_id,
                    reasoning_text=round_text or None,
                )
            if deps.emit_sse:
                line = map_langchain_stream_event(
                    event,
                    run_id=deps.run_id,
                    session_id=deps.session_id,
                    phase="subagent",
                    step_id=step.id,
                    skill_id=step.skill_id,
                    emit_reasoning=False,
                    assistant_stream=deps.assistant_stream,
                )
                if line:
                    await deps.emit_sse(line)
            if event.get("event") == "on_chain_end":
                data = event.get("data") or {}
                out = data.get("output")
                if isinstance(out, dict) and out.get("messages"):
                    output = extract_last_ai_text(out["messages"])
        if not output:
            async with deps.llm_call_scope(
                parent_node_id=parent_node_id,
                phase="subagent",
                step_id=step.id,
                skill_id=step.skill_id,
            ) as llm_node_id:
                result = await subagent.ainvoke(inputs, config=config_sub)
                messages = result.get("messages", [])
                llm_output = None
                for msg in reversed(messages):
                    role = getattr(msg, "type", None) or getattr(msg, "role", None)
                    if role in ("ai", "assistant"):
                        llm_output = msg
                        round_text = extract_reasoning_from_langchain_message(msg)
                        subagent_reasoning_tokens += reasoning_tokens_from_raw(msg)
                        if collector_active and round_text:
                            await collector.append_delta(
                                "subagent",
                                round_text,
                                step_id=step.id,
                                skill_id=step.skill_id,
                            )
                        break
                await deps.finalize_llm_call_to_db(
                    llm_node_id,
                    llm_output or {},
                    phase="subagent",
                    step_id=step.id,
                    skill_id=step.skill_id,
                    reasoning_text=(
                        extract_reasoning_from_langchain_message(llm_output) or None
                        if llm_output is not None
                        else None
                    ),
                )
                output = extract_last_ai_text(messages)
    finally:
        await _finalize_pending_llm_nodes_failed(
            deps,
            pending_llm_nodes,
            step=step,
            error_message="subagent llm call incomplete",
        )

    if collector_active:
        await collector.finalize_segment(
            "subagent",
            reasoning_tokens=subagent_reasoning_tokens,
            step_id=step.id,
            skill_id=step.skill_id,
        )

    return output
