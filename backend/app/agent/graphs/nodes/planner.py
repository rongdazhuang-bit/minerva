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
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.reasoning_collector import (
    extract_reasoning_from_langchain_message,
    reasoning_tokens_from_raw,
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
用户：列出当前目录文件 → steps: [{{"id":"s1","skill_id":"file","goal":"列出当前目录文件"}}]
用户：帮我做一份产品路演的 PPT → steps: [{{"id":"s1","skill_id":"ppt","goal":"制作产品路演演示文稿 pptx"}}]
用户：把这份 PDF 转成幻灯片 → steps: [{{"id":"s1","skill_id":"ppt","goal":"将 PDF 转为 pptx 演示文稿"}}]"""


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

    plan_node_id = uuid.uuid4()
    await agent_repo.begin_run_node(
        deps.db,
        node_id=plan_node_id,
        run_id=deps.run_id,
        parent_node_id=None,
        sequence_idx=1,
        node_type="plan.created",
        node_name="planner",
    )

    structured = deps.model.with_structured_output(Plan, include_raw=True)
    raw_msg = None
    llm_node_id = await deps.begin_llm_call_to_db(
        parent_node_id=plan_node_id,
        phase="planner",
    )
    try:
        result = await structured.ainvoke(planner_messages)
        if isinstance(result, dict):
            parsed = result.get("parsed")
            raw_msg = result.get("raw")
            plan = parsed if isinstance(parsed, Plan) else None
        else:
            plan = result if isinstance(result, Plan) else None
        if plan is None:
            raise ValueError("planner structured output missing Plan")
    except Exception:
        llm_status = "success" if raw_msg is not None else "failed"
        reasoning_text = ""
        if raw_msg is not None and deps.reasoning_collector is not None:
            reasoning_text = extract_reasoning_from_langchain_message(raw_msg)
        await deps.finalize_llm_call_to_db(
            llm_node_id,
            raw_msg or {},
            phase="planner",
            status=llm_status,
            reasoning_text=reasoning_text or None,
            error_message=None if llm_status == "success" else "planner structured output failed",
        )
        fallback = plan_fallback_skill_id(request_text)
        plan = Plan(steps=[PlanStep(id="s1", skill_id=fallback, goal=request_text)])
    else:
        reasoning_text = ""
        if deps.reasoning_collector is not None:
            reasoning_text = extract_reasoning_from_langchain_message(raw_msg)
            if reasoning_text:
                await deps.reasoning_collector.append_delta("planner", reasoning_text)
            await deps.reasoning_collector.finalize_segment(
                "planner",
                reasoning_tokens=reasoning_tokens_from_raw(raw_msg),
            )
        await deps.finalize_llm_call_to_db(
            llm_node_id,
            raw_msg,
            phase="planner",
            reasoning_text=reasoning_text or None,
        )

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

    phase_slice = (deps.usage_tracker.document.get("by_phase") or {}).get("planner") or {}
    if phase_slice:
        await deps.usage_tracker.rollup_children(
            deps.db,
            node_id=plan_node_id,
            child_usage=phase_slice,
        )

    await agent_repo.finalize_run_node(
        deps.db,
        node_id=plan_node_id,
        status="success",
        outputs_json={"step_count": len(plan.steps)},
    )

    return {"plan": plan, "plan_id": plan_id, "current_step_index": 0}
