# Agent 模块优化路线图设计

**日期**：2026-06-22  
**状态**：已实现（2026-06-22 优化路线图 P0–P3 已落地）  
**范围**：在现有 LangGraph Plan-and-Execute 架构上，分四阶段优化延迟/成本、复杂任务可靠性、图级流式与暂停恢复、工程质量；**不**替换 Skill/MCP/SSE v2 契约，**不**引入破坏性 API 变更（除可选新增 SSE 事件类型与配置项）。

**关联文档**：

- [Agent 模块技术设计说明](../../agent-module-design.md)（现行实现）
- [Agent LangGraph 大改设计](2026-05-16-agent-langgraph-redesign-design.md)（基线架构）
- [Agent Skills 管理](2026-05-27-agent-skills-management-design.md)
- [MCP 管理](2026-06-18-mcp-management-design.md)
- [Agent mem0 记忆](2026-06-02-agent-mem0-memory-design.md)

---

## 1. 背景与问题陈述

### 1.1 现状摘要

Minerva Agent v2 已落地：

```text
START → memory.retrieve → planner → executor ⇄ executor → synthesizer → END
                              ↓
                    create_react_agent (per skill step)
```

具备 Skill 插件、MCP 动态工具、双记忆后端、SSE v2 可观测、分层 token 统计、子 Agent 缓存、Planner 多层 fallback 等能力。架构选型正确，属于 LangGraph 生态的主流 Plan-and-Execute 模式。

### 1.2 已识别差距（相对生产最佳实践）

| 类别 | 症状 | 根因 |
|------|------|------|
| 延迟/成本 | 简单寒暄仍走 Planner + ReAct 包装 | 无请求分级路由；`general` 无工具仍用 `create_react_agent` |
| 延迟/成本 | 有 MCP 时子 Agent 编译缓存失效 | `extra_tools` 非空时跳过 cache，且 MCP 注入**所有** Skill |
| 延迟/成本 | 每轮必做 memory.retrieve | 无「本轮是否需要长期记忆」门控 |
| 可靠性 | 子步骤失败后继续执行并合成 | Executor 无 Re-plan / early abort |
| 可靠性 | 极端情况下 subagent 双调用 | `astream_events` 无 output 时 fallback `ainvoke` |
| UX | 多步任务最终合并无流式 | Synthesizer 多步路径使用阻塞 `ainvoke` |
| 能力 | Checkpoint 未用于 pause/resume | 主 Run 使用 `graph.ainvoke`，interrupt 链路未接入主图 |
| 扩展 | 计划步骤严格串行 | 无并行 fan-out |
| 工程 | 文档与测试漂移 | `INDEX.md` vs `INDEX.json`；文档列出的 agent 测试文件不存在 |
| 维护 | Agent 与 `app/llm` 双轨 HTTP | 重试/错误码/日志不统一（有意分离，长期负担） |

### 1.3 优化目标与成功标准

| 目标 | 成功标准（可度量） |
|------|-------------------|
| 降低简单对话成本 | 「纯 general 单轮」Run 的 LLM 调用次数从 ≥2 降至 **1**；P50 首 token 延迟下降 **≥30%**（同模型同网络） |
| 降低 MCP 场景开销 | 有 MCP 时子 Agent **仍命中缓存**（base graph）；MCP 工具按 Skill 白名单注入，单步 tool schema token 不随 MCP 总数线性膨胀 |
| 提升复杂任务成功率 | 子步骤 `failed` 时：可配置 **abort / replan / continue**；Re-plan 后用户可见新 `plan.created` |
| 长任务可中断 | 用户 pause 后 Run 状态 `paused`，resume 从 checkpoint 继续；SSE 发出 `run.paused` / `run.resumed` |
| 工程质量 | 核心路径单元测试 **≥15** 个；`agent-module-design.md` 与代码对齐 |

### 1.4 非目标

- 替换 LangGraph / LangChain 技术栈
- 向量 RAG 作为主链路（mem0 后端维持现状）
- 用户自定义 Skill 包格式变更（仍 `INDEX.json` + `SKILL.md` + `tools.py`）
- 对外开放 Agent API 给第三方集成（仍工作区内 HTTP）
- 一期实现步骤级人工审批 UI（Plan approval 列为 Phase 3 可选）

---

## 2. 总体策略：四阶段路线图

```text
Phase 1 — Quick Wins（2–3 周）
  请求路由 + 记忆门控 + MCP 精准注入 + subagent 双调用修复

Phase 2 — Executor 增强（3–4 周）
  失败策略 + Re-plan + 多步 Synthesizer 流式 + 可选步骤并行

Phase 3 — 图级生命周期（3–4 周）
  astream 主图 + pause/resume + checkpoint 驱动恢复

Phase 4 — 工程质量（持续/并行）
  单元测试 + 文档回填 + app/llm 适配层（可选）
```

各阶段可独立合并；Phase 1 应优先交付。Phase 3 依赖 checkpoint 稳定（现有 `AsyncPostgresSaver` + pool 恢复逻辑可复用）。

---

## 3. Phase 1：Quick Wins

### 3.1 请求分级路由（Intent Router）

**新增节点** `router`（位于 `memory.retrieve` 之前或与之合并决策）：

```text
START → router
  ├─ direct_chat      → direct_responder → END
  ├─ single_skill     → memory.retrieve? → executor (单步) → synthesizer → END
  └─ full_pipeline    → memory.retrieve → planner → executor → synthesizer → END
```

**路由决策（确定性优先，LLM 兜底可选）**：

| 路径 | 条件（按序评估） | 行为 |
|------|------------------|------|
| `direct_chat` | `preferred_skills` 为空；用户消息匹配「简单对话」启发式；**且** `match_skill_for_planner_message` 返回 `general` 或 None；消息长度 ≤ `agent_router_simple_max_chars`（默认 120）；无附件/无「工具向」关键词 | 跳过 Planner；**不**创建 ReAct 子图；`direct_responder` 对截断历史流式 `model.astream`（等同 synthesizer 无 plan 分支） |
| `single_skill` | 已有 `plan_from_preferred_skill` 命中；或触发词唯一匹配某非 general skill | 跳过 Planner LLM；可选跳过 memory（见 §3.2） |
| `full_pipeline` | 其余 | 现有链路 |

**配置项**（`app/config.py` + `.env.example` + `.env.dev`）：

| 变量 | 默认 | 说明 |
|------|------|------|
| `AGENT_ROUTER_ENABLED` | `true` | 总开关 |
| `AGENT_ROUTER_SIMPLE_MAX_CHARS` | `120` | direct_chat 最大字符 |
| `AGENT_ROUTER_LLM_FALLBACK` | `false` | 启发式不确定时是否用轻量 LLM 分类（Phase 1 默认关） |

**状态字段**：`AgentGraphState.route_kind: Literal["direct_chat","single_skill","full_pipeline"]`。

**SSE**：新增可选 `route.decided`，payload `{ "route_kind": "..." }`（前端可忽略）。

**风险与缓解**：

- 误分类 → 默认 `full_pipeline`；启发式单元测试覆盖边界用例；可通过 `AGENT_ROUTER_ENABLED=false` 回滚。

### 3.2 记忆检索门控

**规则**：下列情况 **跳过** `memory.retrieve`（写入空 `memory_context`）：

1. `route_kind == direct_chat`
2. `settings.agent_memory_backend == "sql"` 且工作区+会话下 `agent_long_term_memory` 计数为 0 **且** 用户消息无「回忆/上次/记住」类关键词（关键词表配置化，默认 6 个中文词）
3. Run 请求显式 `skip_memory: true`（新增可选 API 字段，默认 false）

mem0 后端：仍默认检索，但 mem0 失败 degraded 行为不变。

**配置**：`AGENT_MEMORY_RETRIEVE_SKIP_WHEN_EMPTY`（默认 `true`，仅 sql 后端）。

### 3.3 MCP 工具精准注入

**现状问题**：`build_skill_react_agent` 在 `extra_tools` 非空时跳过缓存，并将全部 MCP 工具 merge 进每个 Skill。

**目标架构**：

```text
build_skill_react_agent(model, skill_id, ctx, mcp_tools_for_skill: list[Tool])
  1. base_graph = cache[(skill_id, workspace_id)]  # 仅 skill 内置 tools，不含 MCP
  2. if mcp_tools_for_skill:
       return bind_tools(base_graph, mcp_tools_for_skill)  # 运行时 bind，不污染 cache
  3. else: return base_graph
```

**MCP 分配规则**（Phase 1 最小实现）：

| Skill | MCP 工具 |
|-------|----------|
| `general` | 工作区全部已加载 MCP 工具 |
| 其他 skill | 仅当 `skills/<id>/SKILL.md` 含 `## MCP 工具` 段且列出 tool name 前缀/全名时注入；否则 **不** 注入 MCP |
| 未列出的 MCP | 仅 general 可见 |

**实现要点**：

- `mcp_registry.resolve_langchain_tools` 返回 `(tools, bundles, unavailable)` 不变。
- 新增 `filter_mcp_tools_for_skill(skill_id, all_tools) -> list`。
- `Executor` 传入 per-skill 过滤结果，不再写 `deps.mcp_extra_tools` 全局列表。

### 3.4 修复 subagent 双调用

**规则**：

1. `astream_events` 循环结束后若 `output` 为空，**先**从 checkpoint 或 `on_chain_end` 最后一次 `messages` 再提取一次（已有逻辑加强）。
2. 仅当仍为空 **且** `settings.agent_subagent_ainvoke_fallback`（默认 `false`）为 true 时才 `ainvoke`。
3. 默认关闭 fallback；开启时打 `warning` 日志含 `run_id`、`step_id`。

### 3.5 Phase 1 文件布局

| 路径 | 职责 |
|------|------|
| `graphs/nodes/router.py` | 路由节点 + `route_after_router` |
| `graphs/nodes/direct_responder.py` | 无 plan 流式直答 |
| `infrastructure/request_router.py` | 启发式与配置 |
| `infrastructure/mcp_tool_filter.py` | MCP 按 skill 过滤 |
| `graphs/main.py` | 注册新节点与条件边 |
| `tests/agent/test_request_router.py` | 路由边界 |
| `tests/agent/test_mcp_tool_filter.py` | MCP 过滤 |

### 3.6 Phase 1 测试清单

- 路由：`"你好"` → direct_chat；`"查北京天气"` → single_skill weather；`"先查天气再写文件"` → full_pipeline
- preferred_skill 单选仍跳过 Planner
- MCP：ppt skill 无 MCP 段时不注入；general 注入全部
- subagent：stream 有 output 时不触发 ainvoke
- 记忆：空库 + 普通问题跳过 retrieve（sql 后端）

---

## 4. Phase 2：Executor 增强

### 4.1 步骤失败策略

**配置** `AGENT_STEP_FAILURE_POLICY`：`continue`（默认，兼容现网）| `abort` | `replan`。

| 策略 | Executor 行为 |
|------|---------------|
| `continue` | 现状：标记 failed，追加 `[subagent error: ...]`，继续下一步 |
| `abort` | 标记 failed，`final_answer` 设为结构化错误说明，**跳** synthesizer 合并，直接 END |
| `replan` | 标记 failed，设置 `state.replan_requested = true`，`current_step_index` 复位，回到 planner |

**Re-plan 限制**：

- 每 Run 最多 `agent_max_replan_attempts`（默认 2）
- Planner 提示追加「前次失败步骤与原因」
- 新 plan 持久化为新 `agent_plan` 行或更新 `steps_json`（实现时二选一：**新增 plan 行**，旧 plan `status=superseded`）

**SSE**：`plan.created` 在 replan 时再次发出，`payload.replan_attempt` 递增。

### 4.2 多步 Synthesizer 流式

将 `_invoke_model_text` 多步路径改为 `_stream_model_text`（与无 plan 分支一致），`phase: synthesizer` 推送 `llm.delta`。

**约束**：多步合并场景子 Agent 已流式过 assistant 内容；synthesizer 流式的是**汇总稿**，不与子 Agent 重复（除非模型重复陈述——可接受）。

### 4.3 可选：独立步骤并行（Phase 2 末期）

**条件**：Planner 输出多步且各步 `depends_on` 为空（**扩展 PlanStep**）：

```python
class PlanStep(BaseModel):
    ...
    depends_on: list[str] = Field(default_factory=list)  # 前置 step id
```

**图变更**：Executor 改为 scheduler 节点：

- 找出所有 `depends_on` 已满足的 pending 步骤
- 使用 LangGraph `Send` API 并行 dispatch 子 executor worker
- 全部完成或失败后聚合 `subagent_results`，再决定 synthesizer / replan

**Phase 2 默认**：`depends_on` 字段存在但 Planner 提示要求「默认不填」；并行仅在 `AGENT_PARALLEL_STEPS_ENABLED=true` 时启用。

**非目标**：跨 skill 共享可变沙箱文件的并行写（file/ppt skill 步骤强制串行：Planner 提示 + runtime 检测 `skill_id in ("file","ppt")` 时禁用并行）。

### 4.4 Phase 2 测试清单

- failure policy abort：第二步失败 → 无 synthesizer LLM 调用
- replan：第一步失败 → 第二次 plan.created，步数可能变化
- replan 超限 → abort 并 `run.error`
- 多步 synthesizer 发出 llm.delta
- 并行：两步无依赖时同时 subagent.started（启用开关时）

---

## 5. Phase 3：图级生命周期（astream + pause/resume）

### 5.1 主 Run 从 ainvoke 迁移到 astream

**目标**：`AgentGraphRunService` 使用 `run_lifecycle_service.stream_graph_until_done`（或等价）替代直接 `graph.ainvoke`。

```text
async for mode, chunk in graph.astream(..., stream_mode=["updates","custom"]):
    # updates → 可选 debug SSE
    # interrupt → pause 处理
```

**约束**：

- 对外 SSE 契约不变（仍由 `deps.emit_sse` 驱动，非 LangGraph custom stream 透传）
- `final_state` 从最后一次 update 或 `graph.aget_state` 读取

### 5.2 用户暂停（User Pause）

**API**（新增）：

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `.../runs/{run_id}/pause` | 设置 `agent_run.pause_requested=true` |
| POST | `.../runs/{run_id}/resume` | body `{ "action": "continue" }`，继续图执行 |

**Executor 安全点**：每步 **开始前** 检查 `deps.pause_requested`；为 true 时 `interrupt(UserPausePayload)`。

**DB 字段**（若不存在则 migration patch）：

- `agent_run.pause_requested: bool`
- `agent_run.interrupt_kind: str | null`
- `agent_run.interrupt_payload_json: jsonb | null`
- `agent_run.status` 扩展枚举含 `paused`

**SSE**：`run.interrupted`、`run.paused`；resume 后 `run.resumed`（新增 type）。

**Checkpoint**：`thread_id = {session_id}:{run_id}` 保持不变；resume 使用 `Command(resume=...)`。

### 5.3 Phase 3 前端（最小）

- Run 进行中展示「暂停」按钮 → 调 pause API
- 收到 `run.paused` 后展示「继续」→ 调 resume API（可新开 SSE 或复用长连接，实现计划阶段二选一：**同一 SSE 连接等待 resume 指令** vs **resume 触发新 stream**；推荐 **resume 开新 SSE 订阅 run 事件** 以降低连接复杂度）

### 5.4 Phase 3 非目标

- 工具级 HITL 审批（单独 spec）
- Plan 级人工审批节点（后续 `plan.approval` spec）

---

## 6. Phase 4：工程质量

### 6.1 测试体系

**目录**：`backend/tests/agent/`

**必覆盖模块**：

| 模块 | 测试类型 |
|------|----------|
| `request_router` | 纯函数单元测试 |
| `planner_llm.parse_plan_text` | 单元测试（fence、前缀噪声） |
| `resolve_final_answer_from_subagent_results` | 单元测试 |
| `match_skill_for_planner_message` | 单元测试 |
| `filter_mcp_tools_for_skill` | 单元测试 |
| `build_main_graph` | 编译 smoke test |
| `ChatModelFactory` | mock SysModel 行 |

**集成测试**（可选 CI job，`pytest -m agent_integration`）：

- 使用 fake LLM（LangChain `GenericFakeChatModel`）跑一条 direct_chat 与 full_pipeline。

### 6.2 文档回填

| 文档 | 动作 |
|------|------|
| `docs/agent-module-design.md` | `INDEX.md` → `INDEX.json`；补充 router、MCP 过滤、failure policy；更新目录树 |
| 本 spec | 每阶段完成后更新「实现对照」节 |
| `backend/.env.example` | 同步 Phase 1–3 新配置项 |

### 6.3 Agent ↔ app/llm 统一（可选，低优先级）

**不**让 Agent 调用 `ChatService.complete_chat` 主循环（避免破坏 LangChain 流式/tool bind）。

**推荐**：抽取 `app/llm/strategies/http_common.py` 中 **超时、重试、可重试错误码** 为 `app/llm/http_policy.py`，由 `ChatModelFactory` / `build_direct_endpoint_async_openai` 引用。

**验收**：Agent 上游 429 时行为与 `app/llm` 一致（日志 code 对齐）。

---

## 7. 数据模型与 API 变更摘要

### 7.1 新增/变更 API 字段

**`AgentRunCreateV2`**（可选字段）：

```json
{
  "skip_memory": false
}
```

**新增路由**：见 §5.2。

### 7.2 新增 SSE 事件类型

| type | Phase | payload 要点 |
|------|-------|--------------|
| `route.decided` | 1 | `route_kind` |
| `run.resumed` | 3 | `run_id` |
| `plan.superseded` | 2 | `old_plan_id`, `new_plan_id`（可选） |

均保持 `v: 2` 信封；旧客户端忽略未知 type。

### 7.3 SQL patch（Phase 3）

文件建议：`backend/sql/patches/2026-06-XX-agent-run-pause.sql`

- 扩展 `agent_run.status` 检查约束（若使用 check）
- 新增 `pause_requested`、`interrupt_kind`、`interrupt_payload_json` 列
- **无外键**（符合 Minerva 约定）

---

## 8. 配置项汇总（全新）

| 变量 | 默认 | Phase |
|------|------|-------|
| `AGENT_ROUTER_ENABLED` | `true` | 1 |
| `AGENT_ROUTER_SIMPLE_MAX_CHARS` | `120` | 1 |
| `AGENT_ROUTER_LLM_FALLBACK` | `false` | 1 |
| `AGENT_MEMORY_RETRIEVE_SKIP_WHEN_EMPTY` | `true` | 1 |
| `AGENT_SUBAGENT_AINVOKE_FALLBACK` | `false` | 1 |
| `AGENT_STEP_FAILURE_POLICY` | `continue` | 2 |
| `AGENT_MAX_REPLAN_ATTEMPTS` | `2` | 2 |
| `AGENT_PARALLEL_STEPS_ENABLED` | `false` | 2 |
| `AGENT_GRAPH_ASTREAM_ENABLED` | `false` | 3 |

Phase 3 开关允许灰度：false 时仍走 `ainvoke` 路径。

---

## 9. 风险、回滚与观测

| 风险 | 缓解 |
|------|------|
| Router 误杀复杂短句 | 保守启发式 + 开关 + 指标 |
| Re-plan 循环消耗 token | 硬上限 `agent_max_replan_attempts` |
| 并行步骤沙箱冲突 | file/ppt 禁止并行 |
| astream 回归 SSE 顺序 | 集成测试 + 金丝雀 workspace |
| pause 后 resume 状态不一致 | checkpoint thread_id 固定；resume 前 `aget_state` 校验 |

**观测指标**（日志 event 名）：

- `agent.route.decided`（route_kind）
- `agent.planner.skipped`（bool）
- `agent.memory.skipped`（bool）
- `agent.replan`（attempt）
- `agent.run.paused` / `agent.run.resumed`

**回滚**：各 Phase 独立 feature flag；Phase 1 关闭 `AGENT_ROUTER_ENABLED` 即恢复现网路径。

---

## 10. 实现对照（实施后回填）

| 项 | 状态 |
|----|------|
| Phase 1 Router | 已实现 |
| Phase 1 MCP 过滤 | 已实现 |
| Phase 1 记忆门控 | 已实现 |
| Phase 1 subagent fallback 默认关 | 已实现 |
| Phase 2 failure policy | 已实现 |
| Phase 2 synthesizer 流式 | 已实现 |
| Phase 2 步骤并行 | 已实现（`AGENT_PARALLEL_STEPS_ENABLED`） |
| Phase 3 astream | 已实现（无 pause/resume） |
| Phase 4 测试 + 文档 | 部分（30 单测；文档已回填） |
| Phase 4 app/llm http_policy | 未做（非目标） |

---

## 11. 阶段交付建议

| 里程碑 | 交付物 | PR 粒度 |
|--------|--------|---------|
| M1 | Phase 1 全部 + 单元测试 | 1 PR |
| M2 | Phase 2 failure + synthesizer 流式 | 1 PR |
| M3 | Phase 2 并行（可选） | 1 PR |
| M4 | Phase 3 后端 pause/resume | 1–2 PR |
| M5 | Phase 3 前端 + Phase 4 文档 | 1 PR |
| M6 | app/llm http_policy 抽取 | 1 PR（可选） |

---

*本 spec 基于 2026-06-22 代码库审查；若与运行时行为冲突，以代码为准并在 §10 回填。*
