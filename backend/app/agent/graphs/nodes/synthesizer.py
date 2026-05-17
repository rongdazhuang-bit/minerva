"""Synthesizer node: merge sub-agent outputs into a final user-facing answer."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState


async def _stream_model_text(deps: GraphDeps, messages: list) -> str:
    """Stream model tokens to SSE and return the full concatenated text."""

    parts: list[str] = []
    async for chunk in deps.model.astream(messages):
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
    return "".join(parts)


async def synthesizer_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Produce final_answer from step results or direct model reply."""

    deps: GraphDeps = config["configurable"]["deps"]
    results = state.get("subagent_results") or []
    user_message = state.get("user_message", "")

    if not results:
        text = await _stream_model_text(deps, [HumanMessage(content=user_message)])
        return {"final_answer": text}

    parts = []
    for r in results:
        parts.append(f"[{r.get('capability')}] {r.get('output', '')}")
    blob = "\n\n".join(parts)
    sys = "你是助手。根据各步骤的执行结果，用简洁中文回答用户的原始问题。"
    text = await _stream_model_text(
        deps,
        [
            SystemMessage(content=sys),
            HumanMessage(content=f"用户问题：{user_message}\n\n步骤结果：\n{blob}"),
        ],
    )
    return {"final_answer": text}
