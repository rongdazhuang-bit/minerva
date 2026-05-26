# Agent 思考过程采集、持久化与展示设计

**日期**：2026-05-26  
**状态**：已实现（2026-05-26）  
**范围**：Agent v2 主动开启上游思考模式、各 LLM 节点思考文本双写持久化、SSE v2 扩展、前端独立思考折叠区  
**关联**：[Agent 模块技术设计](../../agent-module-design.md)、[Agent Token 用量设计](2026-05-26-agent-token-usage-design.md)、[Agent LangGraph 大改设计](2026-05-16-agent-langgraph-redesign-design.md)

---

## 1. 背景与目标

### 1.1 背景

当前 Agent v2 对 LLM 思考过程的处理为**被动透传**：

- `ChatModelFactory` 未注入 `enable_thinking` / `reasoning_effort` 等参数
- 仅 Subagent 的 `astream_events` 路径经 `event_mapper.py` 可能转发 `reasoning_content`
- Synthesizer 只读 `content`，丢弃 reasoning
- 数据库无思考文本字段；刷新会话后前端 `reasoning` 丢失
- 前端将思考与运行轨迹混在同一 `assistantTrace` Collapse 内

### 1.2 目标

| 目标 | 说明 |
|------|------|
| 主动开启思考 | 按优先级解析开关，向 upstream 注入思考相关请求参数 |
| 节点级持久化 | Planner / Subagent / Synthesizer 每次 LLM 调用在 `agent_run_node` 记录思考全文 |
| 消息级持久化 | 助手消息在 `agent_message` 记录本轮可见思考（分段结构 + 合并纯文本） |
| SSE 可观测 | 流式推送 reasoning delta、段结束、全部结束事件 |
| 前端独立展示 | 运行过程与思考过程分区；思考区显示 token 数、可折叠、输出完成后自动折叠 |
| Memory 不变 | `memory.persist` **不**采集、不存储、不推送思考，只保留最终抽取结果 |

### 1.3 非目标（本期）

- 将思考内容写回 upstream LLM messages
- 改造 `app/llm` ChatService 主链路
- Memory 抽取节点的思考过程（保持现状）
- reasoning 全文搜索、独立审计页
- 用户自定义 Skill 包内的 thinking 配置 UI

### 1.4 已确认决策

| 项 | 决策 |
|----|------|
| 思考开关优先级 | **前端 Run 参数 > `sys_models.model_config` > `AGENT_ENABLE_THINKING`** |
| 前端 Switch 默认 | **关闭**；请求始终传 `enable_thinking: true/false`（关时覆盖 model_config） |
| 展示粒度 | **单折叠区 + 内部分段**（Planner / Subagent / Synthesizer） |
| 持久化 | **双写**：`agent_run_node.reasoning_text`（每 LLM 调用）+ `agent_message`（助手消息级） |
| Memory | **不带思考**，与现网一致 |
| 实现路径 | **方案 1**：统一 `ReasoningCollector` + 各节点显式接入 + `ChatModelFactory` 注入 |

---

## 2. 思考开关解析

### 2.1 优先级（高 → 低）

1. **Run 请求** `enable_thinking: bool | null`  
   - `true` / `false`：强制开/关  
   - `null` 或字段省略：继续向下解析

2. **`sys_models.model_config`**（JSON 文本，例）：

   ```json
   {
     "enable_thinking": true,
     "thinking_budget": 8192,
     "reasoning_effort": "medium"
   }
   ```

3. **环境变量** `AGENT_ENABLE_THINKING`（`config.py` → `settings.agent_enable_thinking`，默认 `false`）

### 2.2 解析产物

新增 `ThinkingConfig`（`app/agent/infrastructure/thinking_config.py`）：

| 字段 | 说明 |
|------|------|
| `enabled: bool` | 是否向上游请求思考 |
| `extra_body: dict` | 注入 `ChatOpenAI` 的 `model_kwargs.extra_body` |

函数：`resolve_agent_thinking_config(run_flag, model_config_json, settings) -> ThinkingConfig`

- `enabled == false` 时 `extra_body` 为空，不注入
- `model_config` JSON 解析失败：忽略该层，打 debug 日志，不阻断 Run
- 供应商差异：`enable_thinking` / `thinking_budget` / `reasoning_effort` 等自 `model_config` **原样透传**进 `extra_body`（不在 Minerva 硬编码供应商分支表，首期以 JSON 配置为准）

### 2.3 API 与配置变更

| 位置 | 变更 |
|------|------|
| `AgentRunCreateV2` | 新增 `enable_thinking: bool \| null = None` |
| `config.py` | 新增 `agent_enable_thinking: bool = False` |
| `backend/.env.example` / `backend/.env.dev` | 同步 `AGENT_ENABLE_THINKING=false` |
| `ChatModelFactory.from_sys_model_row` | 新增参数 `thinking: ThinkingConfig \| None` |
| `agent_graph_run_service` | Run 入口解析 thinking 并传入 factory |
| `memory_persist_service` 后台任务 | **不**传入 thinking 配置（保持现状） |

---

## 3. 数据库变更

### 3.1 `agent_run_node`

| 列 | 类型 | 说明 |
|----|------|------|
| `reasoning_text` | `TEXT NULL` | 该 `llm.round` 节点对应 LLM 调用的思考全文 |

- 写入对象：`node_type = 'llm.round'` 且 phase 为 `planner` / `subagent` / `synthesizer`
- **`memory.persist` 的 `llm.round` 不写** `reasoning_text`（保持现状）
- Token 数仍用现有 `usage_json.details.reasoning_tokens`，不在此列重复

### 3.2 `agent_message`

| 列 | 类型 | 说明 |
|----|------|------|
| `reasoning_text` | `TEXT NULL` | 该助手消息对应的思考合并纯文本（含阶段标题行） |

**`meta_json.reasoning` 结构**（结构化，供前端分段渲染）：

```json
{
  "segments": [
    {
      "phase": "planner",
      "step_id": null,
      "skill_id": null,
      "text": "...",
      "reasoning_tokens": 64
    },
    {
      "phase": "subagent",
      "step_id": "s1",
      "skill_id": "file",
      "text": "...",
      "reasoning_tokens": 128
    },
    {
      "phase": "synthesizer",
      "step_id": null,
      "skill_id": null,
      "text": "...",
      "reasoning_tokens": 32
    }
  ],
  "reasoning_tokens": 224
}
```

- 仅写入**最终 assistant 消息**（Run 成功且有 `final_answer` 时）
- segments **不含** `memory.persist`
- 若本轮无任何可见思考：`reasoning_text = NULL`，`meta_json` 省略 `reasoning` 键

### 3.3 迁移

- Patch：`backend/sql/patches/2026-05-26-agent-reasoning.sql`
- 同步：`backend/sql/schema_postgresql.sql`
- ORM：`AgentRunNode.reasoning_text`、`AgentMessage.reasoning_text`

---

## 4. 后端采集与持久化

### 4.1 `ReasoningCollector`（挂 `GraphDeps`）

| 方法 | 职责 |
|------|------|
| `append_delta(phase, text, *, step_id, skill_id)` | 内存累积 + 推 SSE `llm.delta` |
| `finalize_segment(phase, *, reasoning_tokens, step_id, skill_id)` | 段结束 + SSE `llm.reasoning.segment_done` |
| `attach_to_llm_round(session, node_id, reasoning_text)` | 更新已插入的 `llm.round.reasoning_text` |
| `build_message_reasoning()` | 生成 `meta_json.reasoning` |
| `build_message_reasoning_text()` | 生成 `agent_message.reasoning_text` 合并文本 |

可见 phase 枚举：`planner` | `subagent` | `synthesizer`

### 4.2 各节点接入

| 节点 | 采集方式 | `agent_run_node` | 进入 message segments |
|------|----------|------------------|------------------------|
| **Planner** | `with_structured_output(..., include_raw=True)` 从 `raw` 的 `additional_kwargs` / metadata 提取 | ✅ `llm.round` | ✅ |
| **Subagent** | 扩展 `event_mapper` + `on_chat_model_end` 汇总 | ✅ 每轮 `llm.round` | ✅ 按 step 分段 |
| **Synthesizer** | `astream` 同时读 `content` 与 `additional_kwargs.reasoning_content` | ✅ | ✅ |
| **Memory** | **不接入** | ❌ | ❌ |

Run 成功写 assistant 消息时：

```python
await agent_repo.append_agent_message(
    ...,
    meta_json={
        "usage": usage_snapshot,
        "reasoning": collector.build_message_reasoning(),  # 无则省略
    },
    reasoning_text=collector.build_message_reasoning_text(),  # 无则 None
)
```

### 4.3 与 usage 的关系

- `reasoning_tokens` 仍由 `openai_usage.py` 从 upstream usage 归一化
- `finalize_segment` / `build_message_reasoning` 中的 `reasoning_tokens` 取自对应 `llm.round.usage_json.details.reasoning_tokens`（缺失则为 0）
- 思考文本与 token 数来源独立：上游未返回 reasoning 文本时，段为空、token 可为 0

---

## 5. SSE v2 事件

### 5.1 扩展 `llm.delta`（`channel = "reasoning"`）

```json
{
  "channel": "reasoning",
  "text": "...",
  "phase": "planner | subagent | synthesizer",
  "step_id": "s1 | null",
  "skill_id": "file | null"
}
```

### 5.2 新增 `llm.reasoning.segment_done`

某可见 phase 的思考流结束：

```json
{
  "phase": "planner",
  "step_id": null,
  "skill_id": null,
  "reasoning_tokens": 64
}
```

### 5.3 新增 `llm.reasoning.done`

用户可见思考**全部结束**（触发前端自动折叠）：

```json
{
  "reasoning_tokens": 224
}
```

**发射时机**：

- 最后一个可见 phase（通常为 Synthesizer）的 reasoning 段 `segment_done` 之后
- 若 Synthesizer 无 reasoning 且无后续可见 phase，则在最后一个有内容的 subagent/planner 段之后补发

**不发射**：`memory.persist` 路径

### 5.4 域模型

- `AgentSseEventType` 增加 `llm_reasoning_segment_done`、`llm_reasoning_done`（或等价命名，与现有 snake 枚举一致）
- 更新 `docs/agent-module-design.md` SSE 表（实现后回填）

---

## 6. 前端 UI

### 6.1 布局（助手气泡内，自上而下）

1. **运行过程** Collapse — 现有 `processLog` / 编排轨迹（**移除** reasoning 混排）
2. **思考过程** Collapse — 位于运行过程**下方**
   - 标题：`思考过程 · {reasoning_tokens} tokens`（i18n）
   - 内容：按 `segments` 分段；段标题 `[Planner]`、`[{skill_id} · {step_id}]`、`[Synthesizer]`
   - 流式：按 `phase` / `step_id` 追加到对应 segment
   - **自动折叠**：收到 `llm.reasoning.done` 后收起；流式期间默认展开
   - 历史消息：默认折叠，可手动展开
   - 无思考内容时：**隐藏**整个思考 Collapse
3. 最终答复 `content`

> **实现说明（2026-05-26）**：轨迹折叠区在正文上方，便于流式时先看编排与思考、后看最终答复。

### 6.2 Run 请求

- 模型选择旁增加「思考模式」Switch
- 默认 **关闭** → 请求体传 `enable_thinking: false`（覆盖 `model_config` 与全局默认）
- 用户打开 → `enable_thinking: true`

### 6.3 会话恢复

| 变更 | 说明 |
|------|------|
| `AgentMessageOut` | 新增 `reasoning_text: str \| null`、`reasoning: dict \| null`（或嵌套 typed schema） |
| `agentMessagesToChat` | 映射 `reasoning_text` + `meta_json.reasoning` → `AgentChatMsg` |
| `AgentChatMsg` | 新增 `reasoningSegments`、`reasoningTokens`；`reasoning` 合并文本可选保留 |
| `mergeAgentChatWithLocal` | 合并时保留本地流式 state，刷新后以服务端为准 |

### 6.4 样式

- 思考区复用/拆分现有 `.agents-page__process-reasoning` 样式
- 运行过程与思考过程两个 Collapse 独立 `openKeys` 状态（`traceOpenKeys` / `reasoningOpenKeys`）

---

## 7. 错误与边界

| 场景 | 行为 |
|------|------|
| 思考开关开但模型不支持 | 段为空；UI 隐藏思考区；Run 正常完成 |
| Run 失败 | 已采集的 `llm.round.reasoning_text` 保留；assistant 消息未写入则无 message 级 reasoning |
| 重新生成 | 截断消息后新 Run 独立采集；旧 message reasoning 随截断删除 |
| 中止 Run | 已推送的 reasoning SSE 保留在本地 state；服务端按已持久化节点为准 |

---

## 8. 实现清单（概要）

### 8.1 Backend

- [ ] `thinking_config.py` + `config.py` + env 同步
- [ ] `ChatModelFactory` 注入 `extra_body`
- [ ] SQL patch + ORM 字段
- [ ] `ReasoningCollector` + `GraphDeps` 集成
- [ ] `planner.py` / `subagent_runner.py` + `event_mapper.py` / `synthesizer.py` 接入
- [ ] `usage_tracker.record_llm_call` 或后续 update 写 `reasoning_text`
- [ ] `agent_graph_run_service` 写 message 双字段
- [ ] `AgentRunCreateV2` / `AgentMessageOut` / router 映射
- [ ] `sse_v2.py` 新事件类型

### 8.2 Frontend

- [ ] 思考模式 Switch（默认关）
- [ ] SSE  handler：`llm.delta` phase 分段、`segment_done`、`reasoning.done` 自动折叠
- [ ] UI：运行过程 / 思考过程分离 Collapse
- [ ] `agentMessagesToChat` / 类型 / i18n

### 8.3 文档回填（实现后）

- [ ] `docs/agent-module-design.md`
- [ ] 本 spec 状态改为「已实现」

---

## 9. 测试要点

- 开关优先级：前端 true 覆盖 model_config false；前端 null 读 model_config；均无则读 env
- Planner + Subagent + Synthesizer 均产生 reasoning 时，DB 双写、SSE 分段、UI 三分段
- Memory persist Run 后：`llm.round` 无 `reasoning_text`，message 无 memory segment
- 刷新会话后思考区从 `agent_message` 还原
- `llm.reasoning.done` 后思考 Collapse 自动收起
- 思考模式关：无 SSE reasoning、无 DB reasoning 字段写入
