"""Planner node: structured Plan generation (skills only; tools loaded later on demand)."""

from __future__ import annotations

import uuid

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.runnables import RunnableConfig

from app.agent.domain.plan import Plan, PlanStep, plan_fallback_skill_id
from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event
from app.agent.graphs.deps import GraphDeps
from app.agent.graphs.state import AgentGraphState
from app.agent.infrastructure.skill_loader import (
    apply_planner_skill_match,
    build_planner_skill_index,
    build_planner_system_intro,
)
from app.config import settings


PLANNER_SYSTEM_TEMPLATE = """你是任务规划器。根据【本轮用户请求】拆分为若干步骤，每步指定 skill_id（{skill_ids}）。

路由以 INDEX 与各 skill 的「何时使用」「Planner 路由」为准；命中触发词时必须选对应 skill_id。
不要把需要「当前服务器时间/日期」的问题分给 general；不要把「列出/读取/写入沙箱文件」分给 general（应选 file）。

只输出符合 schema 的计划，步数不超过 {max_steps}。能一步完成时不要拆多步。

{skill_index}

## 示例
用户：现在几点 → steps: [{{"id":"s1","skill_id":"datetime","goal":"现在几点"}}]
用户：你好 → steps: [{{"id":"s1","skill_id":"general","goal":"你好"}}]
用户：列出当前目录文件 → steps: [{{"id":"s1","skill_id":"file","goal":"列出当前目录文件"}}]"""


async def planner_node(state: AgentGraphState, config: RunnableConfig) -> dict:
    """Produce a structured Plan and persist it."""

    deps: GraphDeps = config["configurable"]["deps"]
    from app.agent.graphs.nodes.memory_nodes import memory_context_text

    mem_block = memory_context_text(state)
    pref = state.get("preferred_skills") or []
    pref_hint = f"\n用户偏好技能：{', '.join(pref)}" if pref else ""
    user_text = state.get("user_message", "")
    sys = PLANNER_SYSTEM_TEMPLATE.format(
        skill_ids=build_planner_system_intro(),
        max_steps=settings.agent_max_plan_steps,
        skill_index=build_planner_skill_index(),
    )
    request_text = (user_text or "").strip()

    planner_messages = [
        SystemMessage(content=sys + pref_hint),
        HumanMessage(
            content=f"{mem_block}\n\n【本轮用户请求】：{request_text}" if mem_block else f"【本轮用户请求】：{request_text}"
        ),
    ]
    structured = deps.model.with_structured_output(Plan)
    try:
        plan = await structured.ainvoke(planner_messages)
    except Exception:
        fallback = plan_fallback_skill_id(request_text)
        plan = Plan(steps=[PlanStep(id="s1", skill_id=fallback, goal=request_text)])

    if not plan.steps:
        fallback = plan_fallback_skill_id(request_text)
        plan = Plan(steps=[PlanStep(id="s1", skill_id=fallback, goal=request_text)])

    plan = apply_planner_skill_match(plan, request_text)
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
