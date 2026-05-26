"""Stream sub-agent runs and map events to SSE v2."""

from __future__ import annotations

import uuid

from langgraph.graph.state import CompiledStateGraph

from app.agent.domain.plan import PlanStep
from app.agent.graphs.deps import GraphDeps
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.chat_history import messages_with_user_input
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
    collector = deps.reasoning_collector
    collector_active = collector is not None and collector.thinking_enabled
    subagent_reasoning_tokens = 0

    async for event in subagent.astream_events(inputs, config=config_sub, version="v2"):
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
            llm_node_id = await deps.record_llm_call_to_db(
                llm_output,
                parent_node_id=parent_node_id,
                phase="subagent",
                step_id=step.id,
                skill_id=step.skill_id,
            )
            round_text = extract_reasoning_from_langchain_message(llm_output)
            subagent_reasoning_tokens += reasoning_tokens_from_raw(llm_output)
            if llm_node_id is not None and round_text:
                await agent_repo.update_run_node_reasoning_text(
                    deps.db,
                    node_id=llm_node_id,
                    reasoning_text=round_text,
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
                llm_node_id = await deps.record_llm_call_to_db(
                    msg,
                    parent_node_id=parent_node_id,
                    phase="subagent",
                    step_id=step.id,
                    skill_id=step.skill_id,
                )
                round_text = extract_reasoning_from_langchain_message(msg)
                subagent_reasoning_tokens += reasoning_tokens_from_raw(msg)
                if collector_active and round_text:
                    await collector.append_delta(
                        "subagent",
                        round_text,
                        step_id=step.id,
                        skill_id=step.skill_id,
                    )
                if llm_node_id is not None and round_text:
                    await agent_repo.update_run_node_reasoning_text(
                        deps.db,
                        node_id=llm_node_id,
                        reasoning_text=round_text,
                    )
                break
        output = extract_last_ai_text(messages)

    if collector_active:
        await collector.finalize_segment(
            "subagent",
            reasoning_tokens=subagent_reasoning_tokens,
            step_id=step.id,
            skill_id=step.skill_id,
        )

    return output
