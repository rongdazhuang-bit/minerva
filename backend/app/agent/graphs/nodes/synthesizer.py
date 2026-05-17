"""Synthesizer node: merge sub-agent outputs into a final user-facing answer."""

from __future__ import annotations

from langchain_core.messages import HumanMessage, SystemMessage

from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState


async def synthesizer_node(state: AgentGraphState, config: dict) -> dict:
    """Produce final_answer from step results or direct model reply."""

    deps: GraphDeps = config["configurable"]["deps"]
    results = state.get("subagent_results") or []
    user_message = state.get("user_message", "")

    if not results:
        resp = await deps.model.ainvoke([HumanMessage(content=user_message)])
        text = getattr(resp, "content", "") or str(resp)
        return {"final_answer": str(text)}

    parts = []
    for r in results:
        parts.append(f"[{r.get('capability')}] {r.get('output', '')}")
    blob = "\n\n".join(parts)
    sys = "你是助手。根据各步骤的执行结果，用简洁中文回答用户的原始问题。"
    resp = await deps.model.ainvoke(
        [
            SystemMessage(content=sys),
            HumanMessage(content=f"用户问题：{user_message}\n\n步骤结果：\n{blob}"),
        ]
    )
    text = getattr(resp, "content", "") or str(resp)
    return {"final_answer": str(text)}
