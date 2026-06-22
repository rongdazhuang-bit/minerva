"""Router node: classify request into direct_chat / single_skill / full_pipeline."""

from __future__ import annotations

from langchain_core.runnables import RunnableConfig

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState, RouteKind
from app.agent.infrastructure.request_router import (
    classify_route,
    plan_for_single_skill_route,
)
from app.core.log import get_logger

log = get_logger(__name__)


async def router_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Decide execution path and optionally materialize a single-step plan."""

    deps: GraphDeps = config["configurable"]["deps"]
    user_message = state.get("user_message", "")
    preferred = state.get("preferred_skills") or []

    route_kind: RouteKind = classify_route(user_message, preferred)
    updates: dict = {
        "route_kind": route_kind,
        "current_step_index": 0,
        "subagent_results": [],
        "replan_requested": False,
        "abort_run": False,
    }

    if route_kind == "single_skill":
        plan = plan_for_single_skill_route(user_message, preferred)
        if plan is None:
            route_kind = "full_pipeline"
            updates["route_kind"] = route_kind
        else:
            updates["plan"] = plan
            log.info(
                "agent planner skipped (single_skill route)",
                event="agent.planner.skipped",
                run_id=str(deps.run_id),
                skill_id=plan.steps[0].skill_id if plan.steps else None,
            )

    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.route_decided,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={"route_kind": route_kind},
            )
        )

    log.info(
        "agent route decided",
        event="agent.route.decided",
        run_id=str(deps.run_id),
        route_kind=route_kind,
    )
    return updates


def route_after_router(state: AgentGraphState) -> str:
    """Route to direct_responder, memory.retrieve, or skip memory path."""

    route = state.get("route_kind") or "full_pipeline"
    if route == "direct_chat":
        return "direct_responder"
    return "memory.retrieve"
