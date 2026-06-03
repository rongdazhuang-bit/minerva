"""Memory retrieve graph node (persist runs in background after ``run.finished``)."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState
from app.config import settings


async def memory_retrieve_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Load long-term memory hits into graph state."""

    deps: GraphDeps = config["configurable"]["deps"]
    query_text = state.get("user_message", "")
    hits = await deps.memory_retrieve.retrieve(
        deps.db,
        workspace_id=deps.workspace_id,
        session_id=deps.session_id,
        query_text=query_text,
    )
    memory_context = await deps.memory_retrieve.build_planner_context(
        deps.db,
        workspace_id=deps.workspace_id,
        session_id=deps.session_id,
        query_text=query_text,
        hits=hits,
    )
    degraded = len(hits) == 0 and settings.agent_memory_backend == "mem0" and bool(
        query_text
    )
    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.memory_retrieved,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "hit_count": len(hits),
                    "sources": [h.source for h in hits[:5]],
                    "backend": settings.agent_memory_backend,
                    "degraded": degraded,
                },
            )
        )
    return {
        "retrieved_memories": hits,
        "memory_context": memory_context,
        "current_step_index": 0,
        "subagent_results": [],
    }


def memory_context_text(state: AgentGraphState) -> str:
    """Format retrieved memories for planner prompts."""

    explicit = (state.get("memory_context") or "").strip()
    if explicit:
        return explicit
    hits = state.get("retrieved_memories") or []
    if not hits:
        return ""
    from app.agent.memory.sql.retrieve import format_memory_hits_for_planner

    return format_memory_hits_for_planner(hits)
