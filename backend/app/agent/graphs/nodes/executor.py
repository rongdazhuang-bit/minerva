"""Executor node: run plan step(s) via skill sub-agents (tools loaded on demand)."""

from __future__ import annotations

import asyncio
import uuid

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END

from app.agent.domain.plan import Plan, PlanStep
from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.nodes.executor_helpers import (
    has_pending_runnable_steps,
    select_steps_to_run,
)
from app.agent.graphs.nodes.subagent_runner import run_subagent_with_stream
from app.agent.graphs.state import AgentGraphState, StepResult
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.mcp_tool_filter import filter_mcp_tools_for_skill
from app.agent.infrastructure.skill_loader import build_skill_react_agent
from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.config import settings
from app.core.log import get_logger

log = get_logger(__name__)


def _failure_abort_message(step: PlanStep, output: str) -> str:
    """User-visible message when abort policy triggers."""

    detail = (output or "").strip()
    if detail:
        return f"任务在步骤 {step.id}（{step.skill_id}）失败，已中止：{detail}"
    return f"任务在步骤 {step.id}（{step.skill_id}）失败，已中止。"


def _handle_step_failure(
    state: AgentGraphState,
    step: PlanStep,
    output: str,
) -> dict | None:
    """Apply failure policy; return state updates or None to continue."""

    policy = settings.agent_step_failure_policy
    if step.status != "failed":
        return None

    if policy == "abort":
        return {
            "final_answer": _failure_abort_message(step, output),
            "abort_run": True,
        }

    if policy == "replan":
        attempt = int(state.get("replan_attempt") or 0)
        max_attempts = settings.agent_max_replan_attempts
        if attempt >= max_attempts:
            return {
                "final_answer": (
                    f"任务在步骤 {step.id}（{step.skill_id}）失败，"
                    f"已重规划 {attempt} 次仍无法完成。"
                ),
                "abort_run": True,
                "error": "agent.replan_exhausted",
            }
        log.info(
            "agent replan requested",
            event="agent.replan",
            run_id=str(state.get("run_id")),
            attempt=attempt + 1,
            step_id=step.id,
        )
        return {
            "replan_requested": True,
            "replan_attempt": attempt + 1,
            "current_step_index": 0,
            "plan": None,
            "plan_id": None,
        }

    return None


async def _execute_one_step(
    deps: GraphDeps,
    state: AgentGraphState,
    plan: Plan,
    step: PlanStep,
    *,
    batch_index: int,
) -> tuple[PlanStep, StepResult, dict | None]:
    """Run one plan step; return updated step, result, and optional failure policy updates."""

    step_idx = next(i for i, s in enumerate(plan.steps) if s.id == step.id)
    step.status = "running"
    plan.steps[step_idx] = step

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
    async with deps.db_write() as session:
        await agent_repo.begin_run_node(
            session,
            node_id=node_id,
            run_id=deps.run_id,
            parent_node_id=None,
            sequence_idx=10 + step_idx + batch_index,
            node_type="subagent.run",
            node_name=step.skill_id,
        )

    ctx = SkillToolContext(workspace_id=deps.workspace_id, chat_model=deps.model)
    mcp_for_skill = filter_mcp_tools_for_skill(step.skill_id, deps.mcp_all_tools or [])
    try:
        subagent = build_skill_react_agent(
            deps.model,
            step.skill_id,
            ctx,
            cache=deps.subagent_cache,
            mcp_tools_for_skill=mcp_for_skill,
        )
        output = await run_subagent_with_stream(
            deps,
            subagent,
            step=step,
            recursion_limit=settings.agent_subagent_recursion_limit,
            parent_node_id=node_id,
        )
        step.status = "success" if output else "failed"
    except Exception as e:
        output = f"[subagent error: {e}]"
        step.status = "failed"

    plan.steps[step_idx] = step
    step_result: StepResult = {
        "step_id": step.id,
        "skill_id": step.skill_id,
        "output": output,
    }

    step_slice = (deps.usage_tracker.document.get("by_step") or {}).get(step.id) or {}
    step_usage = dict(step_slice) if step_slice else {}
    finish_status = "success" if step.status == "success" else "failed"
    async with deps.db_write() as session:
        if step_usage:
            await deps.usage_tracker.rollup_children(
                session,
                node_id=node_id,
                child_usage=step_usage,
            )
        await agent_repo.finalize_run_node(
            session,
            node_id=node_id,
            status=finish_status,
        )
        await agent_repo.insert_terminal_run_node(
            session,
            node_id=uuid.uuid4(),
            run_id=deps.run_id,
            parent_node_id=node_id,
            sequence_idx=0,
            node_type="subagent.finish",
            node_name=step.skill_id,
            status=finish_status,
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
                    "step_usage": step_usage or None,
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

    failure_updates = _handle_step_failure(state, step, output)
    return step, step_result, failure_updates


async def executor_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Execute runnable plan step(s); model chooses tools inside the skill ReAct graph."""

    deps: GraphDeps = config["configurable"]["deps"]

    plan: Plan | None = state.get("plan")
    if plan is None or not plan.steps:
        return {"final_answer": state.get("user_message", "")}

    steps_to_run = select_steps_to_run(plan)
    if not steps_to_run:
        return {}

    if len(steps_to_run) == 1:
        _step, step_result, failure_updates = await _execute_one_step(
            deps, state, plan, steps_to_run[0], batch_index=0
        )
        results = list(state.get("subagent_results") or [])
        results.append(step_result)
        out: dict = {"plan": plan, "subagent_results": results}
        if failure_updates:
            out.update(failure_updates)
        return out

    async def _run(step: PlanStep, batch_index: int):
        return await _execute_one_step(deps, state, plan, step, batch_index=batch_index)

    batch_results = await asyncio.gather(
        *[_run(step, i) for i, step in enumerate(steps_to_run)]
    )

    results = list(state.get("subagent_results") or [])
    failure_updates: dict | None = None
    for _step, step_result, fail in batch_results:
        results.append(step_result)
        if fail and failure_updates is None:
            failure_updates = fail

    out = {"plan": plan, "subagent_results": results}
    if failure_updates:
        out.update(failure_updates)
    return out


def route_after_executor(state: AgentGraphState) -> str:
    """Continue executing, replan, synthesize, or end on abort."""

    if state.get("abort_run") and state.get("final_answer"):
        return END

    if state.get("replan_requested"):
        return "planner"

    plan: Plan | None = state.get("plan")
    if has_pending_runnable_steps(plan):
        return "executor"
    return "synthesizer"
