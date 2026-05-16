# Agent `system_datetime` 技能与工具链路（最小打通）设计说明

**日期**：2026-05-16  
**状态**：待实现  
**范围**：新增 `system_datetime` 技能包；从已选 `skill_ids` 动态加载 `tools.py` 并接入 `AgentRunService` 工具循环；提供技能列表 HTTP API；前端智能体对话页支持 `/` 单选 skill，展示与 API 载荷分离。

---

## 1. 目标与成功标准

### 1.1 目标

- 在 `backend/app/agent/skills/system_datetime/` 实现获取当前系统时间的可执行工具，并注册到 `INDEX.md`。
- 当 run 请求携带非空 `skill_ids` 时，装配对应 `tools.py` 到 `ToolRegistry`，向 LLM 传入 `tools`，支持 **最多 2 轮** LLM（首轮可能 `tool_calls`，执行工具后第二轮流式正文）。
- 新增 `GET /workspaces/{workspace_id}/agent/skills`，供前端解析 `INDEX.md` 展示可选技能。
- 前端 `AgentsPage`：输入以 `/` 开头时弹出 **单选** 技能菜单；气泡展示保留 `/skill_id` 前缀；发给后端的 `user_message` 为剥离前缀后的纯文本，`skill_ids` 单独传递。

### 1.2 成功标准

- 用户选择 `system_datetime` 并提问「现在几点」时，模型可调用 `get_system_datetime`，SSE 轨迹出现 `tool.start` / `tool.result`，最终助手回复含正确时间信息。
- 未选 skill 时行为与现网一致：`tools=None`，不因 `tool_calls` 失败。
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

---

## 4. 后端：`AgentRunService` 工具循环

### 4.1 装配

在现有 `skill.index_load` / `skill.pack_load` 与 system 消息拼接之后：

```python
registry = load_tools_for_skills(skill_ids)
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

### 5.1 列表技能

```
GET /workspaces/{workspace_id}/agent/skills
```

- 鉴权：`require_workspace_member`（与现有 agent 路由一致）。
- 响应体：

```json
{
  "skills": [
    { "id": "system_datetime", "description": "获取当前系统时间（UTC/本地）" },
    { "id": "example_echo", "description": "示例占位技能" }
  ]
}
```

- `id` 来自 `parse_skill_ids_from_index`；`description` 来自 INDEX 行内中文描述，缺省为 `id`。

### 5.2 创建 run（无变更契约）

`POST .../sessions/{session_id}/runs` 仍接受 `skill_ids: string[]`；前端传 `["system_datetime"]` 与剥离后的 `user_message`。

---

## 6. 前端

### 6.1 API 客户端

`minerva-ui/src/api/agent.ts`：

- `AgentSkillListItem { id: string; description: string }`
- `listAgentSkills(workspaceId): Promise<{ skills: AgentSkillListItem[] }>`

### 6.2 `AgentsPage` 状态与交互

| 状态 | 含义 |
|------|------|
| `selectedSkillId` | 当前单选 skill，发送后清空 |
| `skillMenuOpen` | `/` 触发菜单 |

流程：

1. `draft` 以 `/` 开头且未选中 skill → 拉取技能列表，显示单选菜单。
2. 用户选择一项 → `selectedSkillId` 设定，输入框显示 `/system_datetime `（后缀空格便于继续输入）。
3. 发送：
   - 气泡：`/${selectedSkillId} ${body}`.trim() 或仅前缀（body 为空时）
   - API：`user_message` = 去掉 `/^\/?[a-z0-9_]+\s*/i` 后的正文；`skill_ids` = `selectedSkillId ? [selectedSkillId] : []`
4. `skill_ids` 以 state 为准；用户删掉输入框前缀但 state 仍在时仍传 skill。

### 6.3 i18n

新增键（中英）：`agents.skillPickerTitle`、`agents.skillPickerEmpty`、`agents.skillSelectedHint`（可选）。

---

## 7. 测试

| 测试文件 | 覆盖点 |
|----------|--------|
| `test_skill_tools.py` | 加载 `system_datetime`；`get_system_datetime` 返回合法 JSON / ISO |
| `test_skill_loader.py` | INDEX 含 `system_datetime` |
| `test_agent_api.py` | `GET .../skills` 200，列表含 `system_datetime` |
| `test_agent_run_tools.py`（新建或扩展） | mock `ChatService`：round1 `tool_calls` → invoke → round2 文本；无 skill 时 `tools=None` |

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
2. `skill_tools.py` + 单测
3. `AgentRunService` 工具循环 + 单测
4. `GET /agent/skills` + schema/router 测试
5. 前端 API + `AgentsPage` + i18n
6. 端到端手动验证

---

## 10. 与既有 spec 的关系

本设计为 `docs/superpowers/specs/2026-05-15-agent-sse-persistence-design.md` 的 **增量**：仅实现工具循环与 `system_datetime` 的最小切片，细粒度节点树、多轮以上 tool 循环、DB 展示前缀等待后续迭代。
