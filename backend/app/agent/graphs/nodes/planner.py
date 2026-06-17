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
    plan_from_preferred_skill,
)
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.reasoning_collector import (
    extract_reasoning_from_langchain_message,
    reasoning_tokens_from_raw,
)
from app.agent.service.planner_llm import invoke_planner_plan
from app.config import settings


PLANNER_SYSTEM_TEMPLATE = """你是任务规划器。根据【本轮用户请求】拆分为若干步骤，每步指定 skill_id（{skill_ids}）。

路由以 INDEX 与各 skill 的「何时使用」「Planner 路由」为准；命中触发词时必须选对应 skill_id。
不要把需要「当前服务器时间/日期」的问题分给 general；不要把「列出/读取/写入沙箱文件」分给 general（应选 file）。

只输出符合 schema 的计划，步数不超过 {max_steps}。能一步完成时不要拆多步。

## 输出格式（必须遵守）
- 只输出纯 JSON 对象（Plan schema），不要输出任何解释、前后说明或其它文字。
- 禁止使用 markdown 代码块（不要 ```json、不要 ```）。
- 禁止使用 markdown 引用符号 >（不要单独一行 >，不要在 JSON 前加 >）。
- 禁止在 JSON 前或后加任何符号或前缀（如 -、#、引号块等）；响应第一个字符必须是 {{，最后一个字符必须是 }}。
- 输出必须可被 JSON 解析器直接解析。

错误（禁止）：
>
{{"steps": [...]}}

正确：
{{"steps": [{{"id":"s1","skill_id":"weather","goal":"查询天气"}}]}}

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
            content=(
                f"{mem_block}\n\n【本轮用户请求】：{request_text}\n\n"
                "请直接输出 Plan JSON 对象，不要用 >、markdown 代码块或其它前缀。"
                if mem_block
                else f"【本轮用户请求】：{request_text}\n\n请直接输出 Plan JSON 对象，不要用 >、markdown 代码块或其它前缀。"
            )
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

    plan: Plan | None = plan_from_preferred_skill(pref, request_text)
    forced_plan = plan is not None

    if plan is None:
        llm_node_id = await deps.begin_llm_call_to_db(
            parent_node_id=plan_node_id,
            phase="planner",
        )
        llm_finalized = False
        try:
            parsed_plan, raw_msg = await invoke_planner_plan(deps.model, planner_messages)
            if parsed_plan is None:
                await deps.finalize_llm_call_to_db(
                    llm_node_id,
                    {},
                    phase="planner",
                    status="failed",
                    error_message="planner llm invoke failed",
                )
                llm_finalized = True
                plan = Plan(
                    steps=[
                        PlanStep(
                            id="s1",
                            skill_id=plan_fallback_skill_id(request_text),
                            goal=request_text,
                        )
                    ]
                )
            else:
                plan = parsed_plan
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
                    raw_msg or {},
                    phase="planner",
                    status="success",
                    reasoning_text=reasoning_text or None,
                )
                llm_finalized = True
        finally:
            if not llm_finalized:
                await deps.finalize_llm_call_to_db(
                    llm_node_id,
                    {},
                    phase="planner",
                    status="failed",
                    error_message="planner llm call incomplete",
                )

    if plan is None:
        plan = Plan(
            steps=[
                PlanStep(
                    id="s1",
                    skill_id=plan_fallback_skill_id(request_text),
                    goal=request_text,
                )
            ]
        )

    if not plan.steps:
        fallback = plan_fallback_skill_id(request_text)
        plan = Plan(steps=[PlanStep(id="s1", skill_id=fallback, goal=request_text)])

    if not forced_plan:
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
