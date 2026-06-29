# Agent 相对时间锚定（Executor 全局注入）设计说明

**日期**：2026-06-29  
**状态**：已实现  
**范围**：当用户消息含相对时间表述（如「今年」「去年同期」「本季度」）时，在 `executor_node` 层全局预取系统日期并合并 `get_system_datetime` 工具，使 `general` 及任意其它 skill（含 MCP 混合步）能正确解析时间区间。

**关系**：扩展 `docs/superpowers/specs/2026-05-16-agent-system-datetime-skill-design.md`（`datetime` skill 仍负责显式「几点/几号」问答；本 spec 负责含相对时间的分析/查询类请求）。

---

## 1. 目标与成功标准

### 1.1 问题

用户提问示例：

> 请对桂山风电场今年第一季度运行情况分析，并与去年同期对比

Planner 通常路由到 `general`（或配合 MCP 风电工具）。`general` 当前无日期工具，SKILL.md 写明「不涉及日期时间」，模型无法可靠获知「今年」= 哪一年、「去年同期」= 哪个区间，易臆造年份或区间错误。

已有 `datetime` skill 仅覆盖显式时间问题（「现在几点」「今天几号」），不覆盖嵌入业务句中的相对时间词。

### 1.2 目标

- **按需触发**：仅当 `user_message` 命中相对时间词表时激活（非每次 `general` 执行都注入）。
- **全局生效**：无论当前 plan 步执行哪个 `skill_id`，均在 executor 层注入（`general`、`weather`、带 MCP 工具的步均适用）。
- **双保险（方案 C）**：
  - **B 预取注入**：同步读取服务器本地时间，将 ISO 时间块写入子 Agent 的 `step.goal`，首轮即有正确年份；
  - **A 工具合并**：将 `get_system_datetime` 经 `extra_tools` 合并进当前步工具列表，供时区切换或二次确认。

### 1.3 成功标准

- 用户问「桂山风电场今年第一季度运行情况并与去年同期对比」→ 单步 `general`（不拆 `datetime` 步）→ 子 Agent 输入含 `【系统当前时间】` 块 → 正确解析今年 Q1 与去年同期区间。
- 任意 skill 步在执行时，若原始 `user_message` 含相对时间词，该步均获得预取块 + `get_system_datetime` 工具。
- `get_system_datetime` 与 skill 自带同名工具不重复注册（`_merge_tools_by_name` 去重）。
- `datetime` skill 显式路由（「今天几号」）行为不变；若 executor 同时命中词表，允许双注入，不视为错误。
- 单元测试覆盖词表命中/排除、`resolve_system_datetime`、executor 合并逻辑。

### 1.4 非目标（本期）

- Planner 自动拆 `datetime` + 业务 skill 两步。
- 集成 dateparser 等 NLP 日期库（首期仅靠词表 + 模型推理）。
- 前端展示预取时间块（仅子 Agent 内部可见）。
- 将 temporal anchor 持久化到 `agent_message` 或 run 元数据。
- 修改 LLM 训练或 system prompt 全局注入（仅限 executor 步级）。

---

## 2. 方案选型

| 方案 | 说明 | 结论 |
|------|------|------|
| **A. 仅工具合并** | 检测词表 → `extra_tools` 合并 `get_system_datetime` + prompt 提示 | 依赖模型主动调工具，多一轮 LLM |
| **B. 仅预取注入** | 检测词表 → 预取 ISO 写入 `step.goal`，不暴露工具 | 无法切换时区；不符合「其它 skill 可注入工具」 |
| **C. A + B 混合** | 预取保证首轮锚定 + 工具供时区/确认 | **采用** |

**注入策略（用户确认）**：**全局按需** — executor 检测原始 `user_message`，命中则对当前步注入，不按 skill 单独声明。

---

## 3. 架构与数据流

```text
user_message「桂山风电场今年第一季度…去年同期对比」
        │
        ▼
planner_node → Plan(steps=[{skill_id: general, goal: ...}])
        │
        ▼
executor_node (每步均检测 state.user_message，非 step.goal)
  ├─ temporal_context.user_message_needs_temporal_anchor(user_message) → True
  ├─ [B] prefetch_system_datetime(timezone="LOCAL") → {ok, iso, timezone, unix}
  ├─ [B] step_goal = build_temporal_step_goal(step.goal, payload)
  ├─ [A] extras = merge([get_system_datetime], mcp_extra_tools)
  └─ build_skill_react_agent(..., extra_tools=extras)
        │
        ▼
run_subagent_with_stream(step.goal = step_goal)
        │
        ▼
子 Agent：已见预取时间 → 解析「今年 Q1」「去年同期」
         可选调用 get_system_datetime(timezone=...)
```

**多步 Plan**：每一步 executor 均用同一 `user_message` 检测；避免第二步丢失时间锚定。

**Subagent 缓存**：`extra_tools` 非空时 `build_skill_react_agent` 已跳过缓存，无需额外改动。

---

## 4. 新增模块

### 4.1 `temporal_context.py`

路径：`backend/app/agent/infrastructure/temporal_context.py`

| 函数 | 职责 |
|------|------|
| `user_message_needs_temporal_anchor(text: str) -> bool` | 子串匹配相对时间词表；空文本返回 False |
| `prefetch_system_datetime(*, timezone: str = "LOCAL") -> dict` | 调用 `resolve_system_datetime`，返回 `{ok, iso, timezone, unix}` |
| `format_temporal_anchor_prefix(payload: dict) -> str` | 生成 `【系统当前时间】...` 块 |
| `build_temporal_step_goal(base_goal: str, payload: dict) -> str` | 预取块 + 锚定指令 + 原 goal |

### 4.2 相对时间词表（首期）

子串匹配；英文大小写不敏感。

| 类别 | 词 |
|------|-----|
| 年 | 今年、去年、前年、本年度、去年同期、同比 |
| 季 | 本季度、上季度、第一季度、第二季度、第三季度、第四季度、Q1、Q2、Q3、Q4 |
| 月/周 | 本月、上月、本周、上周、月初、月末 |
| 日 | 今天、昨天、前天、明天 |
| 英文 | this year、last year、ytd、mtd、yoy、qoq、same period last year |

**排除（返回 False）**：

- 纯绝对历史日期且无相对词（如单独「2024年3月」无「今年/去年」）。
- 无相对语义的概念问答（如「什么是闰年」— 词表不命中即可）。

**注意**：「今天」在词表中，显式「今天几号」可能同时命中；与 `datetime` skill 路由并存，可接受。

### 4.3 `datetime_tool.py`（共享工具）

路径：`backend/app/agent/infrastructure/datetime_tool.py`

从 `skills/datetime/tools.py` 抽出：

| 导出 | 说明 |
|------|------|
| `resolve_system_datetime(timezone: str) -> dict` | 纯函数；`UTC` / `LOCAL`；供 prefetch 与 tool handler |
| `get_system_datetime` | LangChain `@tool`；返回 JSON 字符串 |

`skills/datetime/tools.py` 改为：

```python
from app.agent.infrastructure.datetime_tool import get_system_datetime

def register_tools(_ctx): return [get_system_datetime]
```

Executor 从 `datetime_tool` 导入 `get_system_datetime` 加入 `extra_tools`。

---

## 5. Executor 改动

文件：`backend/app/agent/graphs/nodes/executor.py`

```python
user_text = (state.get("user_message") or "").strip()
effective_goal = step.goal
extras = list(deps.mcp_extra_tools or [])

if user_message_needs_temporal_anchor(user_text):
    payload = prefetch_system_datetime(timezone="LOCAL")
    effective_goal = build_temporal_step_goal(step.goal, payload)
    extras = _merge_tools_by_name([get_system_datetime], extras)

# 将 effective_goal 传入 run_subagent_with_stream（扩展参数或临时 PlanStep）
subagent = build_skill_react_agent(..., extra_tools=extras or None)
```

### 5.1 预注入文本格式

```text
【系统当前时间】2026-06-29T14:30:00+08:00（LOCAL）
据此解析用户消息中的相对时间（今年=2026年，去年同期=2025年同期），禁止臆造年份。

【时间锚定】若需其它时区或再次确认，可调用 get_system_datetime；否则可直接使用上方时间。

{原 step.goal}
```

### 5.2 `run_subagent_with_stream` 扩展

新增可选参数 `goal_override: str | None = None`；非空时用其替代 `step.goal` 构建 `messages_with_user_input`，不改变 DB 中 plan step 持久化的原 goal。

---

## 6. SKILL.md / Planner / INDEX 调整

### 6.1 `general/SKILL.md`

- 删除「不涉及日期时间」及「仅当…不涉及日期时间」限制。
- 补充：用户消息含相对时间时，executor 会自动预注入系统时间；须基于该时间解析查询区间后再作答或调用其它工具。

### 6.2 `datetime/SKILL.md`

- 在「何时使用」增加说明：显式问当前时刻/日期/星期仍必选本 skill；含「今年/去年同期」等业务相对时间由 executor 全局锚定，Planner **无需**单独拆 `datetime` 步。

### 6.3 `planner.py` 模板

增加示例：

```text
用户：桂山风电场今年第一季度运行情况并与去年同期对比
→ steps: [{"id":"s1","skill_id":"general","goal":"桂山风电场今年第一季度运行情况并与去年同期对比"}]
（不要拆 datetime 步；相对时间由 executor 自动锚定）
```

保留既有规则：「不要把需要当前服务器时间/日期的问题分给 general」指**显式**问时间；含相对时间的**业务分析**可分 general。

### 6.4 `INDEX.json`

`general` 的 `description` 可微调为含「含相对时间表述时自动锚定系统日期」语义（可选，与 SKILL.md 一致即可）。

---

## 7. 示例走通

**输入**：`请对桂山风电场今年第一季度运行情况分析，并与去年同期对比`

| 阶段 | 行为 |
|------|------|
| Planner | 单步 `general`（或未来 `dataset` + MCP） |
| Executor 检测 | 「今年」「第一季度」「去年同期」→ 命中 |
| 预取 | `2026-06-29` LOCAL → 注入 goal |
| 工具 | `get_system_datetime` 合并入 extras |
| 子 Agent 推理 | 今年 Q1 → 2026-01-01 ~ 2026-03-31；去年同期 → 2025-01-01 ~ 2025-03-31 |
| MCP（若有） | 按上述区间调用风电数据查询工具 |

---

## 8. 测试

| 文件 | 覆盖 |
|------|------|
| `tests/agent/test_temporal_context.py`（新建） | 词表命中/排除；`build_temporal_step_goal` 含 iso |
| `tests/agent/test_datetime_tool.py`（新建） | `resolve_system_datetime` JSON 字段合法 |
| `tests/agent/test_executor_temporal.py`（新建或扩展） | mock state 含「今年」→ extras 含工具名；goal_override 含预取块 |

**手动**：Agent 对话输入桂山风电场示例 → 检查 run 轨迹中 subagent 输入或 tool 列表含 `get_system_datetime`；回复中区间年份与服务器当前年一致。

---

## 9. 边界与错误处理

| 场景 | 行为 |
|------|------|
| `user_message` 空 | 不注入 |
| 多步 plan | 每步 executor 均检测同一 `user_message` |
| skill 已自带 `get_system_datetime` | `_merge_tools_by_name` 跳过重复名 |
| 仅 MCP 无内置工具的 skill | 仅 temporal 注入的 `get_system_datetime` |
| prefetch 异常 | 记录 warning；仍尝试仅工具路径；两者均失败则子 Agent 无锚定（退化现网行为） |

---

## 10. 实现顺序建议

1. `datetime_tool.py` + 重构 `datetime/tools.py`
2. `temporal_context.py` + 单测
3. `executor.py` + `subagent_runner.py`（goal_override）
4. `general` / `datetime` SKILL.md + planner 示例
5. executor 集成测试 + 手动验证

---

## 11. 与既有 spec 的关系

| 文档 | 关系 |
|------|------|
| `2026-05-16-agent-system-datetime-skill-design.md` | `datetime` skill 与 `get_system_datetime` 工具来源；本 spec 共享同一工具实现 |
| `2026-06-15-amap-location-weather-skills-design.md` | `weather` 等 skill 在含「今天天气」时可同时获得 temporal 注入 |
| `2026-06-18-mcp-management-design.md` | MCP 工具与 `get_system_datetime` 经同一 `extra_tools` 合并 |

---

## 12. 实现对照（2026-06-29）

| 本 spec | 代码 |
|---------|------|
| §4.3 共享 `datetime_tool` | `backend/app/agent/infrastructure/datetime_tool.py` |
| §4.1 `temporal_context` | `backend/app/agent/infrastructure/temporal_context.py` |
| §5 executor 注入 | `backend/app/agent/graphs/nodes/executor.py` |
| §5.2 `goal_override` | `backend/app/agent/graphs/nodes/subagent_runner.py` |
| §6 SKILL / Planner | `general/SKILL.md`, `datetime/SKILL.md`, `planner.py` |
| §8 单测 | `backend/tests/test_*`（本地 pytest；目录在 `.gitignore`） |
| Plan | `docs/superpowers/plans/2026-06-29-general-skill-temporal-anchor.md` |
