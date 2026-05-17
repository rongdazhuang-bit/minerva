"""Memory retrieve and persist graph nodes."""

from __future__ import annotations

import uuid

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure import repository as agent_repo


async def memory_retrieve_node(state: AgentGraphState, config: dict) -> dict:
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


async def memory_persist_node(state: AgentGraphState, config: dict) -> dict:
    """Persist run summary and optional facts after completion."""

    deps: GraphDeps = config["configurable"]["deps"]
    final = (state.get("final_answer") or "").strip()
    if not final:
        return {}
    try:
        summary = final[:2000]
        await deps.memory_store.insert_summary(
            deps.db,
            workspace_id=deps.workspace_id,
            session_id=deps.session_id,
            content=summary,
            source_run_id=deps.run_id,
        )
        await deps.memory_store.touch_session_summary(
            deps.db, session_id=deps.session_id, summary_text=summary[:8000]
        )
    except Exception:
        pass
    return {}


def memory_context_text(state: AgentGraphState) -> str:
    """Format retrieved memories for planner prompts."""

    hits = state.get("retrieved_memories") or []
    if not hits:
        return ""
    lines = [f"- [{h.kind}/{h.source}] {h.content[:400]}" for h in hits[:10]]
    return "已知记忆：\n" + "\n".join(lines)
