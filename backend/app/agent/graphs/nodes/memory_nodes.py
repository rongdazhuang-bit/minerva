"""Memory retrieve graph node (persist runs in background after ``run.finished``)."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.memory_gate import should_skip_memory_retrieve
from app.config import settings
from app.core.log import get_logger

log = get_logger(__name__)


async def memory_retrieve_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Load long-term memory hits into graph state (or skip when gated)."""

    deps: GraphDeps = config["configurable"]["deps"]
    query_text = state.get("user_message", "")

    memory_count: int | None = None
    if settings.agent_memory_backend == "sql" and settings.agent_memory_retrieve_skip_when_empty:
        async with deps.db_read() as session:
            memory_count = await agent_repo.count_long_term_memory(
                session,
                workspace_id=deps.workspace_id,
                session_id=deps.session_id,
            )

    if await should_skip_memory_retrieve(state, memory_count=memory_count):
        log.info(
            "agent memory retrieve skipped",
            event="agent.memory.skipped",
            run_id=str(deps.run_id),
            route_kind=state.get("route_kind"),
        )
        if deps.emit_sse:
            await deps.emit_sse(
                build_sse_event(
                    event_type=AgentSseEventType.memory_retrieved,
                    run_id=deps.run_id,
                    session_id=deps.session_id,
                    payload={
                        "hit_count": 0,
                        "sources": [],
                        "backend": settings.agent_memory_backend,
                        "degraded": False,
                        "skipped": True,
                    },
                )
            )
        return {
            "retrieved_memories": [],
            "memory_context": "",
            "current_step_index": state.get("current_step_index") or 0,
            "subagent_results": state.get("subagent_results") or [],
        }

    async with deps.db_read() as session:
        hits = await deps.memory_retrieve.retrieve(
            session,
            workspace_id=deps.workspace_id,
            session_id=deps.session_id,
            query_text=query_text,
        )
        memory_context = await deps.memory_retrieve.build_planner_context(
            session,
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
                    "skipped": False,
                },
            )
        )
    return {
        "retrieved_memories": hits,
        "memory_context": memory_context,
        "current_step_index": state.get("current_step_index") or 0,
        "subagent_results": state.get("subagent_results") or [],
    }


def route_after_memory(state: AgentGraphState) -> str:
    """After memory, skip Planner when single_skill route already has a plan."""

    if state.get("route_kind") == "single_skill" and state.get("plan") is not None:
        return "executor"
    return "planner"


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
