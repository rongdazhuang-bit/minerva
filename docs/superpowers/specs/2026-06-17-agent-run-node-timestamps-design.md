# Agent Run Node 时间戳与终态补齐设计

**日期**：2026-06-17  
**状态**：待实现  
**范围**：在 Agent v2 Run 链路中，为 `agent_run_node.started_at` / `finished_at` 建立统一的两阶段写入语义；修复父节点长期停留在 `running` 的问题；子节点失败时向上传播父节点 `failed`  
**关联**：[Agent 模块技术设计](../../agent-module-design.md)、[Agent SSE 持久化设计（历史）](2026-05-15-agent-sse-persistence-design.md)、[Agent LangGraph 大改设计](2026-05-16-agent-langgraph-redesign-design.md)、[Agent Token 用量设计](2026-05-26-agent-token-usage-design.md)

---

## 1. 背景与目标

### 1.1 背景

`agent_run_node` 表与 ORM 已定义 `started_at`、`finished_at`（nullable），但当前所有写入路径均未赋值：

- `insert_run_node` 不接受、不写入时间戳
- 同级 `agent_run` 已在 `create_agent_run` 写 `started_at`、`finalize_agent_run` 写 `finished_at`，可作为模式参考
- 部分父节点（`subagent.run`、`memory.persist`）创建为 `running` 后从未 finalize，长期停留在 `running`
- `llm.round` 节点在 LLM 调用**结束后**一次性插入 `status=success`，无法统计真实 LLM 耗时

### 1.2 目标

| 目标 | 说明 |
|------|------|
| 时间戳落库 | 新 Run 产生的所有 `agent_run_node` 行均正确写入 `started_at` / `finished_at` |
| 两阶段生命周期 | 长生命周期节点（父节点、`llm.round`）采用 `running` → 终态；LLM 调用前 insert，调用后 update |
| 父节点终态修复 | `plan.created`、`subagent.run`、`synthesizer.run`、`memory.persist` 在步骤结束时 finalize |
| 失败传播 | 任一子节点 `failed` → 父节点同步 `failed` |
| 多用途就绪 | 数据可用于运维排查、节点耗时统计、未来 Run 详情 API（本期不实现 API） |

### 1.3 非目标（本期）

- 历史数据中 `started_at` / `finished_at` 为 NULL 的行**不做回填**
- 只读 HTTP API（如 `GET .../runs/{run_id}/nodes`）与前端展示
- Run cancel 时对未完成 node 的批量收尾（`cancel_running_agent_runs_for_session` 仍只更新 `agent_run`）
- 表结构变更（字段已存在）
- 将 streaming delta 逐 token 写入 node

### 1.4 已确认决策

| 项 | 决策 |
|----|------|
| 主要用途 | 运维/调试时间线 + 节点耗时统计 + 未来 API（本期仅落库） |
| 历史回填 | **不需要**，仅保证新 Run 起正确 |
| API | **本期不做**，仅 repository 层落库 |
| `llm.round` 精度 | LLM 调用**前** insert `running` + `started_at`；调用**后** update 终态 + `finished_at` |
| 父节点 | 与 `llm.round` 统一两阶段；顺带修复 stuck `running` |
| 失败传播 | 子节点任意 `failed` → 父节点 `failed` |
| 终态枚举 | 使用现有 `success` / `failed` / `skipped`（不用 `error`） |
| 实现路径 | **方案 1**：Repository 统一 `begin_run_node` / `finalize_run_node` |

---

## 2. 时间戳与 status 语义

| 场景 | `started_at` | `finished_at` | `status` 流转 |
|------|-------------|---------------|---------------|
| 两阶段节点（父节点、`llm.round`） | `begin` 时写入 UTC | `finalize` 时写入 UTC | `running` → `success` / `failed` |
| 瞬时节点（`subagent.finish`、`memory.persist/done` 等） | 插入时写入 | 等于 `started_at` | 插入时即为终态 |
| 进行中 | 已设 | `NULL` | `running` |

- 时间源：`datetime.now(timezone.utc)`
- duration 定义：`finished_at - started_at`（瞬时节点 duration 为 0）

---

## 3. Repository 层 API

在 `backend/app/agent/infrastructure/repository.py` 新增：

### 3.1 `begin_run_node`

插入一行 `status=running` 的节点，写入 `started_at`，`finished_at` 保持 `NULL`。

参数与现有 `insert_run_node` 对齐（`node_id`、`run_id`、`parent_node_id`、`sequence_idx`、`node_type`、`node_name`，以及可选 `inputs_json`、`meta_json`）。

### 3.2 `finalize_run_node`

按 `node_id` 更新终态：

- 写 `finished_at`
- 写 `status`（`success` / `failed` / `skipped`）
- 可选：`outputs_json`、`usage_json`、`reasoning_text`、`error_code`、`error_message`

**内部行为：**

1. 若 `status == failed` 且存在 `parent_node_id` → 向上传播（见 §4）
2. 若该节点为父节点且 finalize 时传入 `success`，但存在 `failed` 子节点 → **强制** `failed`

### 3.3 `insert_terminal_run_node`

用于瞬时子节点（如 `subagent.finish`、`memory.persist/done`）：

- 插入时 `started_at = finished_at = now()`
- `status` 直接为终态
- 若 `status == failed` → 触发父节点失败传播

### 3.4 与现有函数关系

- `insert_run_node`：保留但标记为内部/legacy，新代码统一走 `begin_run_node` / `insert_terminal_run_node`
- `update_run_node_usage` / `update_run_node_reasoning_text`：保留；可在 `finalize_run_node` 时一并传入，或 finalize 前单独 patch

---

## 4. 失败传播规则

```
子节点 finalize(failed)
    → 若 parent 存在且 parent.status == running
        → parent.status = failed, parent.finished_at = now()

父节点 finalize(拟 success)
    → 查询 direct children 是否存在 status == failed
        → 是：parent.status = failed
        → 否：parent.status = success（或调用方显式传入的 failed/skipped）
```

- 传播仅向**直接父节点**递归一层层向上（子 failed → 父 failed → 祖父 failed）
- 已终态的父节点若已为 `failed`，保持 `failed`；若已为 `success` 而后置子节点 failed（理论上不应发生），以 `failed` 覆盖并更新 `finished_at`
- `skipped` 子节点**不**触发父节点 failed

---

## 5. `llm.round` 两阶段改造

### 5.1 API 拆分

重构 `RunUsageTracker` + `GraphDeps`：

| 旧 | 新 |
|----|-----|
| `record_llm_call`（一次性 insert success） | `begin_llm_round` + `finalize_llm_round` |
| `record_llm_call_to_db` | `begin_llm_call_to_db` + `finalize_llm_call_to_db` |

- **begin**：`begin_run_node(node_type=llm.round, status=running)`，返回 `node_id`
- **finalize(success)**：合并 usage、可选 `reasoning_text`，`finalize_run_node(success, ...)`
- **finalize(failed)**：捕获异常路径，`finalize_run_node(failed, error_message=...)`

### 5.2 改造 call site

| 文件 | 改造 |
|------|------|
| `graphs/nodes/planner.py` | `structured.ainvoke` 前 `begin_llm_call_to_db`；成功/异常后 finalize |
| `graphs/nodes/synthesizer.py` | `_stream_model_text`：`astream` 前 begin，循环结束后 finalize；`_invoke_model_text`：`ainvoke` 前 begin，后 finalize |
| `graphs/nodes/subagent_runner.py` | `on_chat_model_start` begin；`on_chat_model_end` finalize；fallback `ainvoke` 同样包裹 try/finally |
| `memory/sql/persist.py` | `invoke_memory_extract` 前 begin `llm.round`，后 finalize |

`usage_tracker.record_llm_call` 的内存累计（`record_call`）仍在 finalize 时执行，与 today 行为一致。

---

## 6. 父节点改造

| 节点 | begin | finalize 时机 | 终态依据 |
|------|-------|---------------|----------|
| `plan.created` | planner 入口 | structured 调用结束 | 无异常且无 failed 子节点 → `success`；异常 → `failed` |
| `subagent.run` | executor 步骤开始 | 步骤结束（写 `subagent.finish` 前/后） | step 失败或子节点 failed → `failed`；否则 `success` |
| `synthesizer.run` | synthesizer 入口 | `_finalize_synthesizer_node` | 无 failed 子节点 → `success` |
| `memory.persist` | persist 入口 | 全部写入成功 / except | success / failed |

**瞬时子节点**（改 `insert_terminal_run_node`）：

| 节点 | 终态 |
|------|------|
| `subagent.finish` | 与 step.status 一致（`success` / `failed`） |
| `memory.persist/done` | `success` |
| `memory.persist/failed`（mem0 异常路径） | `failed` |

---

## 7. 错误处理

| 场景 | 行为 |
|------|------|
| LLM 调用抛异常 | `llm.round` → `failed`；父节点按 §4 传播 |
| planner structured 输出异常 | 走 fallback plan 前仍 finalize `llm.round`（若已开始）；`plan.created` → `success`（fallback 视为完成） |
| executor subagent 异常 | `subagent.run` → `failed`；`subagent.finish` → `failed` |
| memory.persist 整体异常 | 父 `memory.persist` → `failed`；mem0 路径已有 failed 子节点 |
| Run cancel | **本期不处理** node 树；未完成 node 可能仍为 `running` |

---

## 8. 测试

| 类型 | 内容 |
|------|------|
| 单元测试 | `begin_run_node` 写 `started_at`、`finished_at` 为 NULL |
| 单元测试 | `finalize_run_node` 写 `finished_at` 与终态 |
| 单元测试 | 子 `failed` → 父 `failed` + 父 `finished_at` 补齐 |
| 单元测试 | 父 finalize(success) 但有 failed 子 → 父 forced `failed` |
| 单元测试 | `insert_terminal_run_node`：`started_at == finished_at` |
| 集成测试（可选） | 跑通 planner 后 DB 中 `llm.round` 非 NULL 时间戳 |

测试文件建议：`backend/tests/agent/test_run_node_lifecycle.py`

---

## 9. 涉及文件

| 文件 | 变更 |
|------|------|
| `backend/app/agent/infrastructure/repository.py` | 新增 `begin_run_node`、`finalize_run_node`、`insert_terminal_run_node`、失败传播 |
| `backend/app/agent/infrastructure/usage_tracker.py` | 拆分 `begin_llm_round` / `finalize_llm_round` |
| `backend/app/agent/graphs/deps.py` | 拆分 `begin_llm_call_to_db` / `finalize_llm_call_to_db` |
| `backend/app/agent/graphs/nodes/planner.py` | 两阶段 + finalize `plan.created` |
| `backend/app/agent/graphs/nodes/executor.py` | finalize `subagent.run`；瞬时 `subagent.finish` |
| `backend/app/agent/graphs/nodes/synthesizer.py` | LLM 两阶段 + finalize `synthesizer.run` |
| `backend/app/agent/graphs/nodes/subagent_runner.py` | LLM 两阶段（stream 事件） |
| `backend/app/agent/memory/sql/persist.py` | LLM 两阶段 + finalize `memory.persist` |
| `backend/app/agent/memory/mem0/persist.py` | finalize `memory.persist`；瞬时 done/failed |
| `docs/agent-module-design.md` | 实现对照回填 |

---

## 10. 实现对照（以代码为准，2026-06-17）

| Spec 条目 | 当前代码位置 | 备注 |
|-----------|-------------|------|
| `started_at` / `finished_at` 落库 | 未实现 | 全为 NULL |
| `begin_run_node` / `finalize_run_node` | 不存在 | 待新增 |
| `llm.round` 两阶段 | `usage_tracker.record_llm_call` 事后 insert | 待改造 |
| `plan.created` finalize | `planner.py` 仅 `plan_node.status = success` | 无时间戳 |
| `subagent.run` finalize | `executor.py` 无 | stuck `running` |
| `synthesizer.run` finalize | `synthesizer.py` 仅改 status | 无时间戳 |
| `memory.persist` finalize | sql/mem0 persist 无 | stuck `running` |
| 子 failed → 父 failed | 未实现 | 待新增 |
| 历史回填 | — | 明确不做 |
| Run 详情 API | — | 明确不做 |
