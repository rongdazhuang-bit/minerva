"""LangGraph run lifecycle: ainvoke/astream execution."""

from __future__ import annotations

from typing import Any

from langgraph.graph.state import CompiledStateGraph

from app.agent.graphs.state import AgentGraphState
from app.config import settings


async def run_graph_to_completion(
    graph: CompiledStateGraph,
    initial: AgentGraphState,
    run_config: dict[str, Any],
) -> AgentGraphState:
    """Execute graph until completion and return merged final state."""

    if settings.agent_graph_astream_enabled:
        merged: dict[str, Any] = dict(initial)
        async for chunk in graph.astream(
            initial,
            config=run_config,
            stream_mode="updates",
        ):
            if isinstance(chunk, dict):
                for _node, update in chunk.items():
                    if isinstance(update, dict):
                        merged.update(update)
        snap = await graph.aget_state(run_config)
        if snap.values:
            merged.update(dict(snap.values))
        return merged  # type: ignore[return-value]

    result = await graph.ainvoke(initial, config=run_config)
    if isinstance(result, dict):
        return result  # type: ignore[return-value]
    return dict(initial)  # type: ignore[return-value]
