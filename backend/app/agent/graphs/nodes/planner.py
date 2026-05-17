"""Planner node: structured Plan generation."""

from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.domain.intent_routing import detect_datetime_intent
from app.agent.domain.plan import Plan, PlanStep
from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure.chat_history import split_trailing_user_message
from app.config import settings


PLANNER_SYSTEM = """你是任务规划器。根据用户请求拆分为若干步骤，每步指定 capability：
- general：普通对话、总结、无需工具
- file：工作区沙箱内文件/目录操作
- datetime：查询当前日期、时间、星期（必须使用此能力，不要用 general）

只输出符合 schema 的计划，步数不超过 {max_steps}。简单问候只需一步 general。
询问「今天几号」「现在几点」等仅需一步 datetime。"""


def _datetime_fast_plan(user_text: str) -> Plan | None:
    """Build a single-step datetime plan when heuristics match (skip LLM planner)."""

    if detect_datetime_intent(user_text):
        return Plan(steps=[PlanStep(id="s1", capability="datetime", goal=user_text)])
    return None


async def planner_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Produce a structured Plan and persist it."""

    deps: GraphDeps = config["configurable"]["deps"]
    from app.agent.graphs.nodes.memory_nodes import memory_context_text

    mem_block = memory_context_text(state)
    pref = state.get("preferred_capabilities") or []
    pref_hint = f"\n用户偏好能力：{', '.join(pref)}" if pref else ""
    user_text = state.get("user_message", "")
    sys = PLANNER_SYSTEM.format(max_steps=settings.agent_max_plan_steps)
    history = deps.conversation_messages or []
    prior_turns, trailing_user = split_trailing_user_message(history)
    request_text = trailing_user or user_text
    plan = _datetime_fast_plan(request_text)
    if plan is None:
        planner_messages = [
            SystemMessage(content=sys + pref_hint),
            *prior_turns,
            HumanMessage(content=f"{mem_block}\n\n用户请求：{request_text}"),
        ]
        structured = deps.model.with_structured_output(Plan)
        try:
            plan = await structured.ainvoke(planner_messages)
        except Exception:
            if detect_datetime_intent(request_text):
                plan = Plan(
                    steps=[PlanStep(id="s1", capability="datetime", goal=request_text)]
                )
            else:
                plan = Plan(
                    steps=[PlanStep(id="s1", capability="general", goal=user_text)]
                )
    if not plan.steps:
        plan = Plan(steps=[PlanStep(id="s1", capability="general", goal=user_text)])
    plan.steps = plan.steps[: settings.agent_max_plan_steps]

    plan_id = uuid.uuid4()
    from app.agent.domain.db.models import AgentPlan

    row = AgentPlan(
        id=plan_id,
        run_id=deps.run_id,
        steps_json=plan.model_dump(),
        status="active",
    )
    deps.db.add(row)
    await deps.db.flush()

    if deps.emit_sse:
        await deps.emit_sse(
            build_sse_event(
                event_type=AgentSseEventType.plan_created,
                run_id=deps.run_id,
                session_id=deps.session_id,
                payload={
                    "plan_id": str(plan_id),
                    "steps": [s.model_dump() for s in plan.steps],
                },
            )
        )

    from app.agent.infrastructure import repository as agent_repo

    await agent_repo.insert_run_node(
        deps.db,
        node_id=uuid.uuid4(),
        run_id=deps.run_id,
        parent_node_id=None,
        sequence_idx=1,
        node_type="plan.created",
        node_name="planner",
        status="success",
        outputs_json={"step_count": len(plan.steps)},
    )

    return {"plan": plan, "plan_id": plan_id, "current_step_index": 0}
