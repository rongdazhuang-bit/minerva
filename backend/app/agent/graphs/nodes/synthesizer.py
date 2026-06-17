"""Synthesizer node: merge sub-agent outputs into a final user-facing answer."""

from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState, StepResult
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.chat_history import messages_with_user_input, split_trailing_user_message
from app.agent.infrastructure.reasoning_collector import (
    extract_reasoning_from_langchain_chunk,
    extract_reasoning_from_langchain_message,
    reasoning_tokens_from_raw,
)


async def _stream_model_text(
    deps: GraphDeps,
    messages: list,
    *,
    synth_node_id: uuid.UUID,
) -> str:
    """Stream model tokens to SSE and return the full concatenated text."""

    parts: list[str] = []
    reasoning_parts: list[str] = []
    last_usage = None
    collector = deps.reasoning_collector
    collector_active = collector is not None and collector.thinking_enabled
    llm_node_id = await deps.begin_llm_call_to_db(
        parent_node_id=synth_node_id,
        phase="synthesizer",
    )
    status = "success"
    error_message: str | None = None
    stream_error: Exception | None = None

    try:
        async for chunk in deps.model.astream(messages):
            usage_metadata = getattr(chunk, "usage_metadata", None)
            if usage_metadata:
                last_usage = usage_metadata
            reasoning_piece = extract_reasoning_from_langchain_chunk(chunk)
            if reasoning_piece:
                reasoning_parts.append(reasoning_piece)
                if collector_active:
                    await collector.append_delta("synthesizer", reasoning_piece)
            piece = getattr(chunk, "content", None)
            if not isinstance(piece, str) or not piece:
                continue
            parts.append(piece)
            if deps.emit_sse:
                await deps.emit_sse(
                    build_sse_event(
                        event_type=AgentSseEventType.llm_delta,
                        run_id=deps.run_id,
                        session_id=deps.session_id,
                        payload={"channel": "assistant", "text": piece, "phase": "synthesizer"},
                    )
                )
    except Exception as exc:
        status = "failed"
        error_message = str(exc)[:500]
        stream_error = exc
    finally:
        reasoning_text = "".join(reasoning_parts)
        await deps.finalize_llm_call_to_db(
            llm_node_id,
            last_usage or {},
            phase="synthesizer",
            status=status,
            reasoning_text=reasoning_text or None,
            error_message=error_message,
        )
        if collector_active:
            await collector.finalize_segment(
                "synthesizer",
                reasoning_tokens=reasoning_tokens_from_raw(last_usage),
            )

    if stream_error is not None:
        raise stream_error
    return "".join(parts)


async def _invoke_model_text(
    deps: GraphDeps,
    messages: list,
    *,
    synth_node_id: uuid.UUID,
) -> str:
    """Call the model without SSE (sub-agents already streamed assistant text)."""

    async with deps.llm_call_scope(
        parent_node_id=synth_node_id,
        phase="synthesizer",
    ) as llm_node_id:
        resp = await deps.model.ainvoke(messages)
        reasoning_text = extract_reasoning_from_langchain_message(resp)
        collector = deps.reasoning_collector
        if collector is not None and collector.thinking_enabled and reasoning_text:
            await collector.append_delta("synthesizer", reasoning_text)
        await deps.finalize_llm_call_to_db(
            llm_node_id,
            resp,
            phase="synthesizer",
            reasoning_text=reasoning_text or None,
        )
        if collector is not None and collector.thinking_enabled:
            await collector.finalize_segment(
                "synthesizer",
                reasoning_tokens=reasoning_tokens_from_raw(resp),
            )
        content = getattr(resp, "content", None)
        return content.strip() if isinstance(content, str) else ""


async def _finalize_synthesizer_node(deps: GraphDeps, synth_node_id: uuid.UUID) -> None:
    """Roll up synthesizer phase usage onto the synthesizer.run node."""

    phase_slice = (deps.usage_tracker.document.get("by_phase") or {}).get("synthesizer") or {}
    if phase_slice:
        await deps.usage_tracker.rollup_children(
            deps.db,
            node_id=synth_node_id,
            child_usage=phase_slice,
        )
    await agent_repo.finalize_run_node(
        deps.db,
        node_id=synth_node_id,
        status="success",
    )


def _format_subagent_blob(results: list[StepResult]) -> str:
    """Join step outputs for synthesizer merge prompts."""

    parts: list[str] = []
    for r in results:
        parts.append(f"[{r.get('skill_id')}] {r.get('output', '')}")
    return "\n\n".join(parts)


def resolve_final_answer_from_subagent_results(
    results: list[StepResult],
    *,
    user_message: str,
) -> str | None:
    """Return a final answer without a second LLM call when sub-agents already answered.

    A single successful step already streamed its reply via ``llm.delta``; re-synthesizing
    would duplicate the same text on the client.
    """

    if len(results) != 1:
        return None
    output = (results[0].get("output") or "").strip()
    return output if output else None


async def synthesizer_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Produce final_answer from step results or direct model reply."""

    deps: GraphDeps = config["configurable"]["deps"]
    results = state.get("subagent_results") or []
    user_message = state.get("user_message", "")

    direct = resolve_final_answer_from_subagent_results(results, user_message=user_message)
    if direct is not None:
        return {"final_answer": direct}

    synth_node_id = uuid.uuid4()
    await agent_repo.begin_run_node(
        deps.db,
        node_id=synth_node_id,
        run_id=deps.run_id,
        parent_node_id=None,
        sequence_idx=800,
        node_type="synthesizer.run",
        node_name="synthesizer",
    )

    try:
        if not results:
            history = deps.conversation_messages or []
            if history:
                model_messages = history
            else:
                model_messages = messages_with_user_input([], user_message)
            text = await _stream_model_text(deps, model_messages, synth_node_id=synth_node_id)
            await _finalize_synthesizer_node(deps, synth_node_id)
            return {"final_answer": text}

        blob = _format_subagent_blob(results)
        sys = "你是助手。根据各步骤的执行结果，用简洁中文回答用户的原始问题。"
        history = deps.conversation_messages or []
        prior_turns, _ = split_trailing_user_message(history)
        text = await _invoke_model_text(
            deps,
            [
                *prior_turns,
                SystemMessage(content=sys),
                HumanMessage(content=f"用户问题：{user_message}\n\n步骤结果：\n{blob}"),
            ],
            synth_node_id=synth_node_id,
        )
        await _finalize_synthesizer_node(deps, synth_node_id)
        return {"final_answer": text}
    except Exception as exc:
        await agent_repo.finalize_run_node(
            deps.db,
            node_id=synth_node_id,
            status="failed",
            error_message=str(exc)[:500],
        )
        raise
