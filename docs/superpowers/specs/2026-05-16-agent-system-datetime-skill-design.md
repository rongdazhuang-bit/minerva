# Agent `system_datetime` 技能与工具链路（最小打通）设计说明

**日期**：2026-05-16  
**状态**：已实现（2026-05-18 按代码回填；LangGraph v2 集成）  
**范围**：内置技能 id **`datetime`**（非 `system_datetime`）；`get_system_datetime` 工具；经 Planner/executor 子 Agent 调用；列表 API 为 v2 `/skills`。

---

## 1. 目标与成功标准

### 1.1 目标

- 在 `backend/app/agent/skills/system_datetime/` 实现获取当前系统时间的可执行工具，并注册到 `INDEX.md`。
- **技能解析分两档**（见 §3.3）：客户端显式传入非空 `skill_ids` 时 **仅** 加载并执行这些 skill；未传时由服务端根据 `user_message` **自动匹配** INDEX 中的相关 skill（与「只注入总索引、不加载子包」的现网行为升级，而非取消自动能力）。
- 对解析出的 skill 列表装配 `SKILL.md` + `tools.py`，向 LLM 传入 `tools`，支持 **最多 2 轮** LLM（首轮可能 `tool_calls`，执行工具后第二轮流式正文）。
- 新增 `GET /workspaces/{workspace_id}/agent/skills`：**技能列表唯一数据源**为服务端 `INDEX.md`（动态解析），前端 **不得硬编码** skill id；`/` 菜单、描述文案均来自该接口响应。
- 前端 `AgentsPage`：输入以 `/` 开头时弹出 **单选** 技能菜单；气泡展示保留 `/skill_id` 前缀；发给后端的 `user_message` 为剥离前缀后的纯文本，`skill_ids` 单独传递。

### 1.2 成功标准

- 用户选择 `system_datetime` 并提问「现在几点」时，模型可调用 `get_system_datetime`，SSE 轨迹出现 `tool.start` / `tool.result`，最终助手回复含正确时间信息。
- 未通过 `/` 显式选 skill、但用户消息含时间相关语义（如「现在几点」）时，自动激活 `system_datetime` 并完成 tool 调用。
- 显式 `skill_ids: ["system_datetime"]` 时，**不**加载/注册 INDEX 中其他 skill 的文档与工具，即使消息里出现其他领域关键词。
- `GET .../agent/skills` 返回 INDEX 中列出的 skill（含 `system_datetime`）。

### 1.3 非目标

- 同轮多 skill 叠加（前端单选，后端按列表加载但 UI 只传一个 id）。
- 超过 2 轮的 tool 循环、spec 全套 `tool.args_validate` 子节点树。
- 在 `agent_message` 表或 `meta_json` 持久化展示用 `/skill_id` 前缀（仅前端当轮气泡拼接）。
- 为 `example_echo` 实现 `tools.py`。

---

## 2. `system_datetime` 技能包

### 2.1 目录结构

```text
backend/app/agent/skills/
  INDEX.md                          # 增加 system_datetime 条目
  system_datetime/
    SKILL.md                        # 技能说明（何时调用、返回格式）
    tools.py                        # register(registry) 入口
```

### 2.2 `SKILL.md`

说明本技能用于在需要准确「当前时间」时调用工具，避免模型臆造日期；引导模型在涉及日程、截止、相对时间等问题时优先调用 `get_system_datetime`。

### 2.3 `tools.py`

模块导出：

```python
def register(registry: ToolRegistry) -> None: ...
```

注册工具 **`get_system_datetime`**：

| 字段 | 值 |
|------|-----|
| `description` | 返回服务器当前日期时间（ISO-8601）。 |
| `parameters` | JSON Schema object，可选属性 `timezone`：enum `["UTC", "local"]`，默认 `UTC`。 |
| handler | 异步；`UTC` 使用 `datetime.now(timezone.utc)`；`local` 使用服务器本地时区。 |
| 返回值 | JSON 字符串，字段：`iso`（带 `Z` 或 offset）、`timezone`、`unix`（int 秒）。 |

### 2.4 `INDEX.md` 条目

```markdown
- `system_datetime`：获取当前系统时间（UTC/本地）。
```

---

## 3. 后端：工具加载

### 3.1 `skill_tools.py`

路径：`backend/app/agent/infrastructure/skill_tools.py`。

```python
def load_tools_for_skills(skill_ids: list[str]) -> ToolRegistry:
```

行为：

1. 新建空 `ToolRegistry`。
2. 对每个 id：规范化（`strip().lower()`）、校验 `[a-z0-9_]+`。
3. 若 `skills/<id>/tools.py` 存在：`importlib` 导入 `app.agent.skills.<id>.tools`（或等价包路径），调用 `register(registry)`。
4. **工具名冲突**：若 `register` 导致同名重复，抛 `AppError`（`agent.skill.tool_name_conflict`）。
5. 导入/调用异常：记录 `warning`，该 skill 的 tools 跳过（不阻断 run；与 `SKILL.md` 缺失策略一致）。

### 3.2 `skill_loader` 扩展（可选）

可增加 `parse_skill_descriptions_from_index(index_text) -> dict[str, str]`，从 `` - `id`：描述 `` 解析描述，供 API 与测试复用；若实现成本低则一并加入，否则 API 内联解析。

### 3.3 有效 skill 列表解析（`skill_resolver.py`）

路径：`backend/app/agent/infrastructure/skill_resolver.py`。

```python
def resolve_effective_skill_ids(
    *,
    user_message: str,
    requested_skill_ids: list[str],
    index_skill_ids: list[str],
) -> list[str]:
```

| 模式 | 条件 | 行为 |
|------|------|------|
| **显式** | `requested_skill_ids` 去空后非空 | 仅保留在 `index_skill_ids` 中的 id（顺序保持请求顺序）；**不**再跑自动匹配。无效 id 记录 warning 并跳过。 |
| **自动** | `requested_skill_ids` 为空 | 调用 `match_skills_from_message(user_message, index_skill_ids)`，返回 0..N 个相关 skill id。 |

**`match_skills_from_message`（首期启发式，可测、可扩展）**：

- 从 INDEX 解析出的合法 id 集合内匹配。
- 每个 skill 可配置关键词表（首期在 `skill_resolver.py` 内维护 `SKILL_KEYWORDS: dict[str, list[str]]`，`system_datetime` 含：`时间`、`几点`、`日期`、`今天`、`现在`、`星期`、`time`、`date`、`datetime` 等）。
- 用户消息（大小写不敏感）**包含任一关键词**即命中该 skill；多 skill 可同时命中（例如未来新增技能时）。
- 无任何命中 → 返回 `[]`（仅注入 `INDEX.md` 总览，不加载子 `SKILL.md`、不注册 tools，与现网无 tools 行为一致）。

**审计节点**：自动模式下增加 `skill.auto_resolve` 节点，`outputs_json` 含 `matched_ids`、`mode: "auto"`；显式模式为 `mode: "explicit"`、`matched_ids` 即请求列表。

`AgentRunService` **全程使用 `effective_skill_ids`** 替代原始 `skill_ids` 做 `pack_load`、system 拼接、`load_tools_for_skills`。

---

## 4. 后端：`AgentRunService` 工具循环

### 4.1 装配

在 `skill.index_load` 之后、各 `skill.pack_load` 之前调用 `resolve_effective_skill_ids`，得到 `effective_skill_ids`。

在 `skill.pack_load` 与 system 消息拼接之后：

```python
registry = load_tools_for_skills(effective_skill_ids)
tools_payload = registry.get_openai_tools_payload()
tools_arg = tools_payload if tools_payload else None
tool_choice = "auto" if tools_arg else None
```

`llm.context_snapshot.outputs_json` 增加 `tool_names`（已注册工具名列表）。

### 4.2 用户消息

`append_agent_message(..., content=user_message)` 使用 API 入参（**已剥离 `/skill_id` 的纯文本**）。展示前缀仅由前端负责。

### 4.3 LLM 轮次（最多 2 轮）

```text
round_1: stream with tools → assistant (+ optional tool_calls)
  if tool_calls:
    persist assistant
    for each tool_call:
      emit tool.start (minerva SSE)
      invoke registry
      persist role=tool message
      emit tool.result
    rebuild api_messages from DB
    round_2: stream with tools → assistant
  else:
    persist assistant → finish

if round_2 still has tool_calls:
  fail with agent.tool_loop_exceeded (or log + treat as terminal assistant without further tools)
```

移除现有「无 tools 却收到 tool_calls 即失败」分支中对 **已启用 tools** 场景的误判；仅当 `tools_arg is None` 且上游返回 `tool_calls` 时保持原失败逻辑。

### 4.4 SSE 事件

工具执行时发送已有类型：

- `MinervaStreamEventKind.tool_start` + `MinervaToolSnapshot`（`name`、`tool_call_id`、`arguments_preview` 截断）
- `MinervaStreamEventKind.tool_result` + `result_preview` 截断

预览字段经 `redact_json` / 长度上限处理。

### 4.5 节点树（首期最小）

每个 tool call 一行父节点：`node_type=tool.invocation`，`node_name=tool:<name>#<short_id>`，`status=success|failed`。不实现 `tool.args_validate` / `tool.result_normalize` 子节点。

---

## 5. HTTP API

### 5.1 列表技能（动态，供前端 `/` 菜单）

```
GET /workspaces/{workspace_id}/agent/skills
```

- 鉴权：`require_workspace_member`（与现有 agent 路由一致）。
- **数据源**：每次请求读取磁盘 `skills/INDEX.md` 并解析（与 `skill_loader` 共用解析逻辑）；INDEX 增删 skill 后 **无需改前端代码** 即可出现在菜单中。
- 响应体（Pydantic `AgentSkillListOut`）：

```json
{
  "skills": [
    { "id": "system_datetime", "description": "获取当前系统时间（UTC/本地）" },
    { "id": "example_echo", "description": "示例占位技能" }
  ]
}
```

- `id`：来自 `parse_skill_ids_from_index`。
- `description`：来自 INDEX 行 `` - `id`：描述 ``；解析不到则用 `id`。
- 可选校验：仅返回 `skills/<id>/SKILL.md` 存在的项（避免 INDEX 笔误）；`tools.py` 有无不影响是否出现在列表中。

### 5.2 创建 run（无变更契约）

`POST .../sessions/{session_id}/runs` 仍接受 `skill_ids: string[]`；前端传 `["system_datetime"]` 与剥离后的 `user_message`。

---

## 6. 前端

### 6.1 API 客户端

`minerva-ui/src/api/agent.ts`：

- `AgentSkillListItem { id: string; description: string }`
- `listAgentSkills(workspaceId): Promise<{ skills: AgentSkillListItem[] }>` — **唯一**获取可选 skill 的入口。

### 6.2 `AgentsPage` 状态与交互

| 状态 | 含义 |
|------|------|
| `selectedSkillId` | 当前单选 skill，发送后清空 |
| `skillMenuOpen` | `/` 触发菜单 |
| `skillsQuery` | `useQuery(['agent-skills', workspaceId], listAgentSkills)`，进入页面或首次输入 `/` 时拉取 |

流程：

1. `draft` 以 `/` 开头 → 若尚未加载则 `listAgentSkills`；菜单项 **仅渲染 API 返回的 `skills[]`**（`id` + `description`），支持输入过滤（按 id / description 子串）。
2. 用户选择一项 → `selectedSkillId` 设为 API 返回的 `id`，输入框显示 `/${id} `（后缀空格便于继续输入）。
3. 发送：
   - 气泡：`/${selectedSkillId} ${body}`.trim() 或仅前缀（body 为空时）
   - API：`user_message` = 去掉 `/^\/?[a-z0-9_]+\s*/i` 后的正文。
   - API：`skill_ids` = `selectedSkillId ? [selectedSkillId] : []`（**空数组表示走后端自动匹配**，不表示禁用 skill）。
4. `skill_ids` 以 state 为准；用户删掉输入框前缀但 state 仍在时仍传显式 skill。
5. 未选 skill 时前端 **不传** 或传 `[]`，由后端 `skill_resolver` 根据消息内容决定是否加载 `system_datetime` 等。

### 6.3 i18n

新增键（中英）：`agents.skillPickerTitle`、`agents.skillPickerEmpty`、`agents.skillLoading`（拉取列表中）、`agents.skillSelectedHint`（可选）。**skill 名称与描述以 API 为准**，不写死 `system_datetime` 等 id。

---

## 7. 测试

| 测试文件 | 覆盖点 |
|----------|--------|
| `test_skill_tools.py` | 加载 `system_datetime`；`get_system_datetime` 返回合法 JSON / ISO |
| `test_skill_loader.py` | INDEX 含 `system_datetime` |
| `test_skill_resolver.py` | 显式模式仅返回请求 id；空请求 +「现在几点」命中 `system_datetime`；空请求 + 无关文本返回 `[]` |
| `test_agent_api.py` | `GET .../skills` 200，列表含 `system_datetime` |
| `test_agent_run_tools.py`（新建或扩展） | mock `ChatService`：round1 `tool_calls` → invoke → round2 文本；自动匹配命中时启用 tools |

手动：前端 `/` → 选 `system_datetime` → 问时间 → 助手轨迹含 `[tool.start]`。

---

## 8. 错误码

| 代码 | 场景 |
|------|------|
| `agent.tool_loop_exceeded` | 第二轮仍返回 `tool_calls` |
| `agent.skill.tool_name_conflict` | 多 skill 注册同名工具 |
| `agent.unexpected_tool_calls` | 未传 tools 但上游返回 tool_calls（保留） |

---

## 9. 实现顺序建议

1. `system_datetime` 技能包 + `INDEX.md`
2. `skill_resolver.py` + 单测
3. `skill_tools.py` + 单测
4. `AgentRunService`（`effective_skill_ids` + 工具循环）+ 单测
5. `GET /agent/skills` + schema/router 测试
6. 前端 API + `AgentsPage` + i18n
7. 端到端手动验证（显式 `/system_datetime` 与自动「现在几点」各一条）

---

## 10. 与既有 spec 的关系

原 v1 增量设计已由 LangGraph 取代。当前见 `2026-05-16-agent-langgraph-redesign-design.md` §14。

---

## 11. 实现对照（以代码为准，2026-05-18）

| 本 spec 原文 | 当前代码 |
|--------------|----------|
| skill id `system_datetime` | **`datetime`**（`skills/datetime/`，`INDEX.md`） |
| 目录 `skills/system_datetime/` | `skills/datetime/` |
| `skill_resolver` + `skill_ids` | **无**；`preferred_skills` 仅提示 Planner |
| `AgentRunService` 2 轮 tool 循环 | `create_react_agent`，`agent_subagent_recursion_limit=16` |
| `GET .../agent/skills` | `GET .../agent/v2/skills` |
| 前端 `/` 单选 + `skill_ids` | **未接线**（`AgentsPage` 中 `preferred_skills: []`） |
| 工具名 `get_system_datetime` | **一致**（`skills/datetime/tools.py`） |
| SSE `tool.start` | `tool.started`（SSE v2） |
