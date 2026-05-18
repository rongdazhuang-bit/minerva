# Agent 模块（方案 3 + 真 SSE + 会话/run/细粒度节点持久化）设计说明

**日期**：2026-05-15  
**状态**：已废止（2026-05-18）；由 LangGraph + SSE v2 替代，见 `2026-05-16-agent-langgraph-redesign-design.md`  
**范围**：在 `backend/app/agent/` 实现智能体抽象：技能包（`INDEX.md` + 子 skill 文档 + 可注册 tools）、通过 **`app/llm` 最小扩展**调用模型、**默认真·SSE** 对外输出统一事件流；**服务端持久化**会话与消息以支持跨请求续写；**类 Dify 工作流**的 **细粒度节点树**（每节点含 id、类型、名称、输入/输出快照、状态与时间线）。应用日志（stdout/平台）仍保留，与 `run_id` 对齐。

---

## 1. 目标与成功标准

### 1.1 目标

- **架构**：方案 3 — `agent` 负责编排与观测封装；**上游 HTTP/SDK 调用集中在 `app/llm`**（策略 + `ChatService`），为其增加 **tools + 多形态 messages** 与 **流式路径上的 tool_calls 拼装**能力；现有不传 `tools` 的 LLM 行为保持不变。
- **技能包**：根目录 `backend/app/agent/skills/`，**总索引用固定文件名 `INDEX.md`**；子目录各 skill，含 `SKILL.md` 与可选 `tools.py`（或等价注册入口）；装配时注入文档（A）并注册可执行 tools（B）。
- **对外 API**：工作区 + 鉴权下的 HTTP 接口，供前端「智能体」使用；**核心循环**在 `agent` 的 **service** 层，供 HTTP 与内部 Python 共用。
- **默认传输**：**单条 SSE**（`text/event-stream`），`data:` 后为 JSON envelope，`type` 区分 `assistant_delta`、`tool_start`、`tool_result`、`log`/`step`、`run_started`、`run_finished`、`error` 等。
- **持久化**：`agent_session`、`agent_message`（权威对话历史）、`agent_run`、`agent_run_node`（**细粒度、可树形**）；支持 **跨请求**仅带 `session_id` + 新用户输入，由服务端 **续写并重建 messages**。
- **观测**：**应用日志**（`run_id`、分步摘要、脱敏）与 **DB 节点树**并存；**不在 DB 存 api_key**，`inputs_json`/`outputs_json` 必须经过 **脱敏与大小上限**。

### 1.2 成功标准

- 前端默认走 **真流式**：模型正文增量以 **上游流式 chunk** 为主数据源映射到 `assistant_delta`（允许极小的合并缓冲以降低 IO 碎片，但语义上仍是流式）。
- 工具调用存在时：能在 **流结束**后得到完整 `tool_calls`，执行工具，**持久化**后继续下一轮 **流式** LLM，对外仍为 **同一条 SSE**。
- 同一会话第二次请求：服务端能基于 **`agent_message`** 还原 OpenAI 风格多轮（含 `tool` / `tool_calls`），模型行为与首轮衔接正确。
- 每次 run 可在 DB 中展开为 **明显细于「一轮 LLM / 一次 tool」** 的节点树，且单节点行数 **有上限策略**（见 §5），避免按 token 一行打爆库表。

### 1.3 非目标（首期可不实现）

- 将 **每个上游 token chunk** 各写一行 `agent_run_node`（显式排除）。
- 全量 SSE 事件逐条落库（若未来需要「逐事件回放」，另立 `agent_run_event` 表或对象存储，本 spec 不纳入首期必达）。
- 复杂多租户计费、任意代码执行型 skill（文档只注入；执行仅白名单 tools）。

---

## 2. 模块与目录

```text
backend/app/agent/
  skills/
    INDEX.md                 # 固定：总说明 + 引入子 skill
    <skill_id>/
      SKILL.md
      tools.py               # 可选：注册 tools
  domain/                    # SSE envelope、节点类型枚举、DTO
  infrastructure/            # SkillLoader、ToolRegistry、脱敏/截断
  service/                   # AgentRunService：流式编排、落库、SSE 发射
  api/                       # FastAPI 路由（工作区维度）
  domain/db/models.py        # ORM：session / message / run / run_node
```

`app/core/api/router.py` 聚合注册 `agent` 路由（实现阶段接入）。

---

## 3. 与 `app/llm` 的集成（最小扩展）

- **阻塞 `complete`**：支持 `tools`、`tool_choice`、`messages` 为 OpenAI 兼容结构（含 `assistant.tool_calls`、`tool`）。
- **流式 `stream`**：同样传入 `tools`；消费异步 chunk 流，**增量累积**：
  - `content` 片段 → 映射给 agent 层，由 agent 发 `assistant_delta`；
  - `tool_calls` 片段（含跨 chunk 的 `id`/`name`/`arguments` 拼接）→ 在 `finish_reason` 或流结束判定完整后，再进入工具执行。
- **错误与重试**：仍走 `ChatService` 与既有 `AppError` 映射；agent 将错误转为 SSE `error` 事件并更新 `agent_run` / 相关节点 `failed`。

---

## 4. SSE 事件模型（单流）

统一 envelope（示例字段，实现可微调命名）：

- `v`：整数 schema 版本。
- `type`：`run_started` | `log` | `step` | `tool_start` | `tool_result` | `assistant_delta` | `run_finished` | `error`。
- `run_id`、`ts`、以及各 type 的专属 payload。

**与 DB**：SSE 面向实时 UI；**细粒度审计**以 `agent_run_node` 树为准，不要求与每个 delta 一一对应行数。

---

## 5. 细粒度 `agent_run_node` 设计（用户要求：比「一轮 LLM / 一次 tool」更细）

### 5.1 通用列（表结构，与先前草案一致并强化语义）

表名：`agent_run_node`

| 列 | 说明 |
|----|------|
| `id` | UUID，节点主键（对外「节点 id」） |
| `run_id` | FK → `agent_run.id` |
| `parent_node_id` | 可空，自引用；**子节点挂父节点** |
| `sequence_idx` | 同 `(run_id)` 或同 `(run_id, parent_node_id)` 下排序（实现时二选一并加唯一约束，见 §5.3） |
| `node_type` | 机器类型（小写 snake） |
| `node_name` | 展示名 |
| `status` | `pending` / `running` / `success` / `failed` / `skipped` |
| `inputs_json` / `outputs_json` | JSONB，**脱敏 + 截断**后写入 |
| `error_code` / `error_message` | 可空 |
| `started_at` / `finished_at` | 可空 |
| `meta_json` | 扩展：如 segment_index、字节数、上游 finish_reason |

### 5.2 节点类型与树形模板（首期必达清单）

**A. 每次「用户消息触发的 run」根部（可选）**

- `run.root`（无父或父为空）：`inputs_json` 放用户输入摘要、选用的 `skill_id` 列表、模型名等非密钥信息。

**B. 技能装配（比单节点更细）**

- `skill.index_load`：读取 `skills/INDEX.md` 的结果摘要（路径、字节数、hash）。
- `skill.pack_load`：**每个**激活的子 skill 各一行（父可为 `skill.assembly` 或 `run.root`）：
  - `node_type=skill.pack_load`，`node_name=<skill_id>`，`outputs_json`：`SKILL.md` 元数据（长度、hash），**不存全文**（全文在内存用于请求；库中仅存摘要）。

**C. 每一轮「上游流式 LLM 调用」（在 tool 循环内可能多次）**

父节点：`llm.round`（`node_name` 建议带轮次序号，如 `round_2`）

其子节点（**顺序执行**，均挂在 `llm.round` 下）：

1. `llm.context_snapshot`：`outputs_json` 含 messages 条数、各 role 计数、**最后一条 user 摘要**、tools 名称列表。
2. `llm.upstream_request`：`inputs_json` 为脱敏后的请求摘要（模型、温度、max_tokens、tools 清单）；**禁止** api_key。
3. `llm.stream_segment`：**多条**子节点，按 **分段策略**（§5.4）切割；每段 `outputs_json` 含 `text_delta` 聚合片段、`chunk_count`、`first_token_at`/`last_token_at`（可选）。
4. `llm.tool_calls_parsed`：当本轮解析出完整 `tool_calls` 时一行；`outputs_json` 为结构化 tool_calls（参数仍脱敏/截断）。
5. `llm.finish`：`outputs_json` 含 `finish_reason`、`usage` 摘要。

若无 `tool_calls` 且正常结束，`llm.tool_calls_parsed` 可跳过或记空对象。

**D. 每一次工具调用（每个 `tool_call_id`）**

父节点：`tool.invocation`（`node_name` 建议 `tool:<name>#<short_id>`）

子节点：

1. `tool.args_validate`：`inputs_json` 摘要；失败则 `failed` 并中止后续子节点。
2. `tool.execute`：`inputs_json`/`outputs_json` 为入参/出参摘要（截断）。
3. `tool.result_normalize`：将返回值格式化为 message 的摘要写入 `outputs_json`。

**说明**：上述已显著细于「一轮 LLM 一条、一次 tool 一条」；若仍要更细，可在 `llm.stream_segment` 下再挂 `llm.stream_flush`（按 flush 次数）——首期 **不推荐** 再拆一层以免行数失控，除非把 §5.4 阈值调大。

### 5.3 `sequence_idx` 与唯一性

推荐：`(run_id, parent_node_id, sequence_idx)` **唯一**；根层 `parent_node_id IS NULL` 时单独处理唯一（PostgreSQL 可用部分唯一索引或 sentinel）。实现阶段在迁移中明确。

### 5.4 流式分段策略（控制 `llm.stream_segment` 行数）

可配置（环境变量或 settings），默认值示例：

- `AGENT_NODE_STREAM_SEGMENT_MAX_CHARS`：默认 **2048**（每累计满 N 字符落一段新 `llm.stream_segment`）。
- **或** `AGENT_NODE_STREAM_SEGMENT_MAX_CHUNKS`：默认 **50**（每处理 M 个上游 chunk 落一段，**与字符阈值取先达到者**）。

**硬上限**：单 run 的 `llm.stream_segment` 最大行数（如 **500**），超出后合并到同节点 `meta_json.overflow=true` 并打 `log` 级告警。

---

## 6. 其余表（与会话续写）

### 6.1 `agent_session`

- `workspace_id`、`created_by`、`title`、`agent_key`、`status`、`meta_json`、`created_at`、`updated_at`。
- 索引：`workspace_id + updated_at`。

### 6.2 `agent_message`

- `session_id`、`seq`（**唯一 (session_id, seq)**）、`role`、`content`、`tool_calls_json`、`tool_call_id`、`tool_name`、`meta_json`、`run_id`、`created_at`。
- 服务端权威历史；跨请求由 `seq` 有序重建 messages。

### 6.3 `agent_run`

- `id` 即 **`run_id`**（SSE 与日志对齐）、`session_id`、`workspace_id`、`triggered_by`、`status`、`started_at`、`finished_at`、`model`、`provider_kind`、`error_code`、`error_message`、`usage_json`、`request_meta_json`。
- 索引：`session_id + started_at`。

---

## 7. HTTP 行为（摘要）

- `POST .../agent/sessions` → 创建 `agent_session`。
- `POST .../agent/sessions/{session_id}/runs`（默认 `Accept`/`stream` 约定为 SSE）→ 创建 `agent_run`、写用户 `agent_message`、装配 skills、流式调用 `llm`、穿插写 `agent_run_node` 树、流式结束写 assistant/tool 相关 `agent_message`、完结 `agent_run`。

---

## 8. 安全与合规

- **api_key** 不入任何 JSONB 列；日志同样脱敏。
- `inputs_json`/`outputs_json`：**单字段最大**（如 64KB 或 128KB）超出截断并 `meta_json.truncated=true`。
- 工具白名单 + 单工具超时 + 参数大小限制。

---

## 9. 测试要点（首期）

- 流式 + 无工具：segment 节点数量符合阈值；`assistant_delta` 连贯。
- 流式 + 单轮 tool：节点树包含 `llm.*` 与 `tool.*` 子结构；`agent_message` 可重建第二轮。
- 跨请求：第二次请求仅 `session_id` + 新 user，历史不丢。
- 回归：`llm` 旧接口不传 tools 行为不变。

---

## 10. 自审（占位 / 矛盾 / 范围）

- **节点更细**已通过 **树形子节点 + `llm.stream_segment` 分段策略**落地；**明确排除** per-token 一行。
- **`INDEX.md`** 为固定总索引文件名。
- 若产品后续要求「SSE 级回放」，需另表或外链，不在本期范围。

---

## 11. 下一步

~~评审通过后：使用 **writing-plans** 产出实现计划~~（已由 v2 大改取代。）

---

## 12. 实现对照（以代码为准，2026-05-18）

**本 spec 描述的 v1 Agent 编排与 SSE envelope 已不再实现。** 下列为**仍沿用**与**已替代**部分：

| 本 spec | 当前代码 |
|---------|----------|
| `POST .../agent/sessions`（无 v2） | 仅 `.../agent/v2/...`（`backend/app/agent/api/v2/router.py`） |
| 自定义 SSE：`assistant_delta`、`tool_start` 等 | **SSE v2**：`llm.delta`、`tool.started`、`run.started`（`domain/sse_v2.py`） |
| `AgentRunService` + `ToolRegistry` | `AgentGraphRunService` + LangGraph |
| 细粒度节点 `llm.round` / `skill.index_load` | `plan.created`、`subagent.run`/`finish`、`memory.persist`（后台） |
| 表 `agent_session` / `agent_message` / `agent_run` / `agent_run_node` | **仍使用**（`domain/db/models.py`） |

权威说明：`docs/agent-module-design.md`、`2026-05-16-agent-langgraph-redesign-design.md` §14。
