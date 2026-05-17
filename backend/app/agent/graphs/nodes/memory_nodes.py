"""Memory retrieve graph node (persist runs in background after ``run.finished``)."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState


async def memory_retrieve_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Load long-term memory hits into graph state."""

    deps: GraphDeps = config["configurable"]["deps"]
    hits = await deps.memory_store.retrieve(
        deps.db,
        workspace_id=deps.workspace_id,
        session_id=deps.session_id,
        query_text=state.get("user_message", ""),
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
                },
            )
        )
    return {"retrieved_memories": hits, "current_step_index": 0, "subagent_results": []}


def memory_context_text(state: AgentGraphState) -> str:
    """Format retrieved memories for planner prompts."""

    hits = state.get("retrieved_memories") or []
    if not hits:
        return ""
    lines = [f"- [{h.kind}/{h.source}] {h.content[:400]}" for h in hits[:10]]
    return "已知记忆：\n" + "\n".join(lines)
