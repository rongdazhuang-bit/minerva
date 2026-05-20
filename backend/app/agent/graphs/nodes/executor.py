"""Executor node: run one plan step via a skill sub-agent (tools loaded on demand)."""

from __future__ import annotations

import uuid

from langchain_core.runnables import RunnableConfig

from app.agent.domain.plan import Plan
from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.nodes.subagent_runner import run_subagent_with_stream
from app.agent.graphs.state import AgentGraphState, StepResult
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.skill_loader import build_skill_react_agent
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.config import settings


async def executor_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Execute the current plan step; model chooses tools inside the skill ReAct graph."""

    deps: GraphDeps = config["configurable"]["deps"]
    plan: Plan | None = state.get("plan")
    if plan is None or not plan.steps:
        return {"final_answer": state.get("user_message", "")}

    idx = int(state.get("current_step_index") or 0)
    if idx >= len(plan.steps):
        return {}

    step = plan.steps[idx]
    step.status = "running"
    plan.steps[idx] = step

    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.plan_step_updated,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={"step_id": step.id, "status": "running", "skill_id": step.skill_id},
            )
        )
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.subagent_started,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={"skill_id": step.skill_id, "step_id": step.id},
            )
        )

    node_id = uuid.uuid4()
    await agent_repo.insert_run_node(
        deps.db,
        node_id=node_id,
        run_id=deps.run_id,
        parent_node_id=None,
        sequence_idx=10 + idx,
        node_type="subagent.run",
        node_name=step.skill_id,
        status="running",
    )

    ctx = SkillToolContext(workspace_id=deps.workspace_id, chat_model=deps.model)
    try:
        subagent = build_skill_react_agent(
            deps.model,
            step.skill_id,
            ctx,
            cache=deps.subagent_cache,
        )
        output = await run_subagent_with_stream(
            deps,
            subagent,
            step=step,
            recursion_limit=settings.agent_subagent_recursion_limit,
        )
        step.status = "success" if output else "failed"
    except Exception as e:
        output = f"[subagent error: {e}]"
        step.status = "failed"

    plan.steps[idx] = step
    step_result: StepResult = {
        "step_id": step.id,
        "skill_id": step.skill_id,
        "output": output,
    }
    results = list(state.get("subagent_results") or [])
    results.append(step_result)

    await agent_repo.insert_run_node(
        deps.db,
        node_id=uuid.uuid4(),
        run_id=deps.run_id,
        parent_node_id=node_id,
        sequence_idx=0,
        node_type="subagent.finish",
        node_name=step.skill_id,
        status=step.status,
        outputs_json={"chars": len(output)},
    )

    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.subagent_finished,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "skill_id": step.skill_id,
                    "step_id": step.id,
                    "status": step.status,
                },
            )
        )
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.plan_step_updated,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "step_id": step.id,
                    "status": step.status,
                    "skill_id": step.skill_id,
                },
            )
        )

    return {
        "plan": plan,
        "current_step_index": idx + 1,
        "subagent_results": results,
    }


def route_after_executor(state: AgentGraphState) -> str:
    """Continue executing plan steps or move to synthesizer."""

    plan: Plan | None = state.get("plan")
    if plan is None:
        return "synthesizer"
    idx = int(state.get("current_step_index") or 0)
    if idx < len(plan.steps):
        return "executor"
    return "synthesizer"
