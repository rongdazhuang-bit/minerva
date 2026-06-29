# General Skill 相对时间锚定 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 当用户消息含「今年/去年同期」等相对时间词时，executor 全局预取系统日期并合并 `get_system_datetime`，使 general 及任意 skill 能正确解析时间区间。

**Architecture:** 抽出共享 `datetime_tool.py`；新增 `temporal_context.py` 负责词表检测、预取与 goal 拼装；`executor_node` 在构建 subagent 前调用 `prepare_executor_temporal_context`；`run_subagent_with_stream` 支持 `goal_override` 传入增强后的 goal。双保险：预取块写入 goal + `get_system_datetime` 经 `extra_tools` 合并（与 MCP 工具同路径）。

**Tech Stack:** Python 3.12 / FastAPI / LangGraph ReAct / LangChain tools / pytest

**Spec:** `docs/superpowers/specs/2026-06-29-general-skill-temporal-anchor-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/agent/infrastructure/datetime_tool.py` | `resolve_system_datetime` + `get_system_datetime` 共享实现 |
| `backend/app/agent/skills/datetime/tools.py` | 薄包装，re-export `get_system_datetime` |
| `backend/app/agent/infrastructure/temporal_context.py` | 词表检测、预取、goal 拼装、executor 上下文准备 |
| `backend/app/agent/infrastructure/skill_loader.py` | 公开 `merge_tools_by_name`（由 `_merge_tools_by_name` 别名） |
| `backend/app/agent/graphs/nodes/executor.py` | 调用 temporal 准备逻辑 |
| `backend/app/agent/graphs/nodes/subagent_runner.py` | `goal_override` 参数 |
| `backend/app/agent/skills/general/SKILL.md` | 移除「不涉及日期时间」 |
| `backend/app/agent/skills/datetime/SKILL.md` | 说明相对时间由 executor 锚定 |
| `backend/app/agent/graphs/nodes/planner.py` | 增加桂山风电场示例 |
| `backend/tests/test_datetime_tool.py` | `resolve_system_datetime` 单测 |
| `backend/tests/test_temporal_context.py` | 词表与 goal 拼装单测 |
| `backend/tests/test_executor_temporal.py` | `prepare_executor_temporal_context` 单测 |

---

### Task 1: 共享 `datetime_tool.py`

**Files:**
- Create: `backend/app/agent/infrastructure/datetime_tool.py`
- Modify: `backend/app/agent/skills/datetime/tools.py`
- Create: `backend/tests/test_datetime_tool.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_datetime_tool.py`:

```python
"""Tests for shared system datetime tool."""

from __future__ import annotations

import json

from app.agent.infrastructure.datetime_tool import get_system_datetime, resolve_system_datetime


def test_resolve_system_datetime_utc_has_required_fields() -> None:
    payload = resolve_system_datetime("UTC")
    assert payload["ok"] is True
    assert payload["timezone"] == "UTC"
    assert isinstance(payload["iso"], str)
    assert "T" in payload["iso"]
    assert isinstance(payload["unix"], int)


def test_resolve_system_datetime_local_has_required_fields() -> None:
    payload = resolve_system_datetime("LOCAL")
    assert payload["ok"] is True
    assert payload["timezone"] == "local"
    assert isinstance(payload["iso"], str)
    assert isinstance(payload["unix"], int)


def test_get_system_datetime_tool_returns_json_string() -> None:
    raw = get_system_datetime.invoke({"timezone": "UTC"})
    data = json.loads(raw)
    assert data["ok"] is True
    assert data["timezone"] == "UTC"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_datetime_tool.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.infrastructure.datetime_tool'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/agent/infrastructure/datetime_tool.py`:

```python
"""Shared system datetime resolution and LangChain tool for agent skills."""

from __future__ import annotations

import json
from datetime import datetime
from datetime import timezone as dt_timezone
from typing import Any

from langchain_core.tools import tool


def resolve_system_datetime(timezone: str = "UTC") -> dict[str, Any]:
    """Return current server time as a dict (ok, iso, timezone, unix)."""

    tz = (timezone or "UTC").strip().upper()
    if tz == "LOCAL":
        now = datetime.now().astimezone()
        tz_label = "local"
    else:
        now = datetime.now(dt_timezone.utc)
        tz_label = "UTC"
    iso = now.isoformat().replace("+00:00", "Z") if tz_label == "UTC" else now.isoformat()
    return {
        "ok": True,
        "iso": iso,
        "timezone": tz_label,
        "unix": int(now.timestamp()),
    }


@tool
def get_system_datetime(timezone: str = "UTC") -> str:
    """返回服务器当前日期时间（JSON：ok, iso, timezone, unix）。"""

    return json.dumps(resolve_system_datetime(timezone), ensure_ascii=False)
```

`backend/app/agent/skills/datetime/tools.py`（全文替换为薄包装）:

```python
"""Datetime skill tools (``register_tools`` + JSON ok contract)."""

from __future__ import annotations

from typing import Any

from app.agent.infrastructure.datetime_tool import get_system_datetime
from app.agent.infrastructure.skill_tool_context import SkillToolContext


def register_tools(_ctx: SkillToolContext) -> list[Any]:
    """Register datetime tools for on-demand skill loading."""

    return [get_system_datetime]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_datetime_tool.py -v`

Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/datetime_tool.py backend/app/agent/skills/datetime/tools.py backend/tests/test_datetime_tool.py
git commit -m "feat(agent): extract shared datetime_tool for get_system_datetime"
```

---

### Task 2: `temporal_context.py` 词表与 goal 拼装

**Files:**
- Create: `backend/app/agent/infrastructure/temporal_context.py`
- Create: `backend/tests/test_temporal_context.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_temporal_context.py`:

```python
"""Tests for relative-time anchor detection and goal formatting."""

from __future__ import annotations

from app.agent.infrastructure.temporal_context import (
    build_temporal_step_goal,
    format_temporal_anchor_prefix,
    prefetch_system_datetime,
    user_message_needs_temporal_anchor,
)


def test_user_message_needs_temporal_anchor_matches_relative_phrases() -> None:
    assert user_message_needs_temporal_anchor("桂山风电场今年第一季度运行情况") is True
    assert user_message_needs_temporal_anchor("并与去年同期对比") is True
    assert user_message_needs_temporal_anchor("What is YoY growth this year?") is True


def test_user_message_needs_temporal_anchor_rejects_plain_text() -> None:
    assert user_message_needs_temporal_anchor("你好") is False
    assert user_message_needs_temporal_anchor("") is False
    assert user_message_needs_temporal_anchor("什么是闰年") is False


def test_prefetch_system_datetime_returns_ok_payload() -> None:
    payload = prefetch_system_datetime(timezone="LOCAL")
    assert payload["ok"] is True
    assert "iso" in payload


def test_build_temporal_step_goal_includes_anchor_and_original_goal() -> None:
    payload = prefetch_system_datetime(timezone="LOCAL")
    goal = build_temporal_step_goal("分析桂山风电场", payload)
    assert "【系统当前时间】" in goal
    assert payload["iso"] in goal
    assert "分析桂山风电场" in goal
    assert "get_system_datetime" in goal


def test_format_temporal_anchor_prefix_contains_iso() -> None:
    payload = prefetch_system_datetime(timezone="LOCAL")
    prefix = format_temporal_anchor_prefix(payload)
    assert prefix.startswith("【系统当前时间】")
    assert payload["iso"] in prefix
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_temporal_context.py -v`

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Write minimal implementation**

`backend/app/agent/infrastructure/temporal_context.py`:

```python
"""Relative-time detection and executor temporal anchor helpers."""

from __future__ import annotations

from typing import Any

from app.agent.infrastructure.datetime_tool import get_system_datetime, resolve_system_datetime

# Substring triggers; English matching is case-insensitive via lowered haystack.
_TEMPORAL_ANCHOR_PHRASES: tuple[str, ...] = (
    "今年",
    "去年",
    "前年",
    "本年度",
    "去年同期",
    "同比",
    "本季度",
    "上季度",
    "第一季度",
    "第二季度",
    "第三季度",
    "第四季度",
    "本月",
    "上月",
    "本周",
    "上周",
    "月初",
    "月末",
    "今天",
    "昨天",
    "前天",
    "明天",
    "q1",
    "q2",
    "q3",
    "q4",
    "this year",
    "last year",
    "ytd",
    "mtd",
    "yoy",
    "qoq",
    "same period last year",
)


def user_message_needs_temporal_anchor(text: str) -> bool:
    """Return True when the message contains relative-time phrases needing a date anchor."""

    haystack = (text or "").strip()
    if not haystack:
        return False
    lowered = haystack.lower()
    return any(phrase in lowered if phrase.isascii() else phrase in haystack for phrase in _TEMPORAL_ANCHOR_PHRASES)


def prefetch_system_datetime(*, timezone: str = "LOCAL") -> dict[str, Any]:
    """Synchronously prefetch server datetime for injection into sub-agent goals."""

    return resolve_system_datetime(timezone)


def format_temporal_anchor_prefix(payload: dict[str, Any]) -> str:
    """Format the prefetched datetime block for sub-agent consumption."""

    iso = payload.get("iso", "")
    tz = payload.get("timezone", "LOCAL")
    return f"【系统当前时间】{iso}（{tz}）\n据此解析用户消息中的相对时间（今年/去年/本季度/去年同期等），禁止臆造年份。"


def build_temporal_step_goal(base_goal: str, payload: dict[str, Any]) -> str:
    """Prepend temporal anchor instructions and prefetched time to the plan step goal."""

    anchor = format_temporal_anchor_prefix(payload)
    instruction = (
        "【时间锚定】若需其它时区或再次确认，可调用 get_system_datetime；"
        "否则可直接使用上方时间。"
    )
    body = (base_goal or "").strip()
    return f"{anchor}\n\n{instruction}\n\n{body}".strip()


def prepare_executor_temporal_context(
    *,
    user_message: str,
    step_goal: str,
    mcp_extra_tools: list[Any] | None,
) -> tuple[str, list[Any]]:
    """Return effective goal and merged extra tools when temporal anchor is required."""

    from app.agent.infrastructure.skill_loader import merge_tools_by_name

    extras = list(mcp_extra_tools or [])
    if not user_message_needs_temporal_anchor(user_message):
        return step_goal, extras
    payload = prefetch_system_datetime(timezone="LOCAL")
    effective_goal = build_temporal_step_goal(step_goal, payload)
    extras = merge_tools_by_name([get_system_datetime], extras)
    return effective_goal, extras
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/test_temporal_context.py -v`

Expected: 5 passed (may fail until Task 3 exports `merge_tools_by_name` — if so, complete Step 3 of Task 3 first, then re-run)

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/temporal_context.py backend/tests/test_temporal_context.py
git commit -m "feat(agent): add temporal_context for relative-time anchor detection"
```

---

### Task 3: 公开 `merge_tools_by_name`

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_loader.py`
- Create: `backend/tests/test_executor_temporal.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_executor_temporal.py`:

```python
"""Tests for executor temporal context preparation."""

from __future__ import annotations

from app.agent.infrastructure.temporal_context import prepare_executor_temporal_context


def test_prepare_executor_temporal_context_no_anchor_unchanged() -> None:
    goal, extras = prepare_executor_temporal_context(
        user_message="你好",
        step_goal="打招呼",
        mcp_extra_tools=[],
    )
    assert goal == "打招呼"
    assert extras == []


def test_prepare_executor_temporal_context_injects_goal_and_tool() -> None:
    goal, extras = prepare_executor_temporal_context(
        user_message="桂山风电场今年第一季度运行情况并与去年同期对比",
        step_goal="分析桂山风电场",
        mcp_extra_tools=[],
    )
    assert "【系统当前时间】" in goal
    assert "分析桂山风电场" in goal
    assert len(extras) == 1
    assert getattr(extras[0], "name", None) == "get_system_datetime"


def test_prepare_executor_temporal_context_dedupes_datetime_tool() -> None:
    from app.agent.infrastructure.datetime_tool import get_system_datetime

    goal, extras = prepare_executor_temporal_context(
        user_message="今年营收同比",
        step_goal="分析营收",
        mcp_extra_tools=[get_system_datetime],
    )
    assert "【系统当前时间】" in goal
    assert len(extras) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/test_executor_temporal.py -v`

Expected: FAIL with `ImportError: cannot import name 'merge_tools_by_name'`

- [ ] **Step 3: Export public alias in skill_loader**

在 `backend/app/agent/infrastructure/skill_loader.py` 中，于 `_merge_tools_by_name` 定义之后追加：

```python
merge_tools_by_name = _merge_tools_by_name
```

并在 `build_skill_react_agent` 内将 `extras = _merge_tools_by_name(tools, extras)` 保持不变（或改为 `merge_tools_by_name`，二选一，行为相同）。

若文件有 `__all__` 则不必添加；无则无需新建。

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_temporal_context.py tests/test_executor_temporal.py -v`

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/skill_loader.py backend/tests/test_executor_temporal.py
git commit -m "feat(agent): export merge_tools_by_name for temporal executor extras"
```

---

### Task 4: `subagent_runner` 支持 `goal_override`

**Files:**
- Modify: `backend/app/agent/graphs/nodes/subagent_runner.py`

- [ ] **Step 1: Add `goal_override` parameter**

在 `run_subagent_with_stream` 签名中增加 `goal_override: str | None = None`，并将构建 inputs 的一行改为：

```python
effective_goal = (goal_override or step.goal or "").strip()
inputs = {"messages": messages_with_user_input(history, effective_goal)}
```

完整函数签名：

```python
async def run_subagent_with_stream(
    deps: GraphDeps,
    subagent: CompiledStateGraph,
    *,
    step: PlanStep,
    recursion_limit: int,
    parent_node_id: uuid.UUID,
    goal_override: str | None = None,
) -> str:
```

- [ ] **Step 2: Verify import still works**

Run: `cd backend && python -c "from app.agent.graphs.nodes.subagent_runner import run_subagent_with_stream; print('ok')"`

Expected: `ok`

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/graphs/nodes/subagent_runner.py
git commit -m "feat(agent): allow goal_override in subagent runner"
```

---

### Task 5: `executor_node` 集成 temporal 上下文

**Files:**
- Modify: `backend/app/agent/graphs/nodes/executor.py`

- [ ] **Step 1: Import and wire temporal preparation**

在 `executor.py` 顶部增加 import：

```python
from app.agent.infrastructure.temporal_context import prepare_executor_temporal_context
```

在 `ctx = SkillToolContext(...)` 之后、`build_skill_react_agent` 之前插入：

```python
    user_text = (state.get("user_message") or "").strip()
    effective_goal, extra_tools = prepare_executor_temporal_context(
        user_message=user_text,
        step_goal=step.goal,
        mcp_extra_tools=deps.mcp_extra_tools,
    )
```

将原来的：

```python
        subagent = build_skill_react_agent(
            deps.model,
            step.skill_id,
            ctx,
            cache=deps.subagent_cache,
            extra_tools=deps.mcp_extra_tools or None,
        )
        output = await run_subagent_with_stream(
            deps,
            subagent,
            step=step,
            recursion_limit=settings.agent_subagent_recursion_limit,
            parent_node_id=node_id,
        )
```

替换为：

```python
        subagent = build_skill_react_agent(
            deps.model,
            step.skill_id,
            ctx,
            cache=deps.subagent_cache,
            extra_tools=extra_tools or None,
        )
        output = await run_subagent_with_stream(
            deps,
            subagent,
            step=step,
            recursion_limit=settings.agent_subagent_recursion_limit,
            parent_node_id=node_id,
            goal_override=effective_goal if effective_goal != step.goal else None,
        )
```

说明：仅当 goal 被增强时才传 `goal_override`，避免无意义重复。

- [ ] **Step 2: Run full agent-related tests**

Run: `cd backend && python -m pytest tests/test_datetime_tool.py tests/test_temporal_context.py tests/test_executor_temporal.py -v`

Expected: all passed

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/graphs/nodes/executor.py
git commit -m "feat(agent): inject temporal anchor in executor for relative-time queries"
```

---

### Task 6: SKILL.md 与 Planner 文档更新

**Files:**
- Modify: `backend/app/agent/skills/general/SKILL.md`
- Modify: `backend/app/agent/skills/datetime/SKILL.md`
- Modify: `backend/app/agent/graphs/nodes/planner.py`

- [ ] **Step 1: Update general SKILL.md**

`backend/app/agent/skills/general/SKILL.md` 全文替换为：

```markdown
## 工具名称：`general`

### 功能
处理通用对话任务（闲聊、解释、翻译、写作、逻辑推理、总结已有文本、业务分析等）。

当用户消息含相对时间表述（如「今年」「去年同期」「本季度」）时，executor 会自动预注入系统当前时间，并可能提供 `get_system_datetime` 工具；须基于该时间解析查询区间后再作答或调用其它工具。

### 何时使用
**仅当**用户需求属于以下类型，且**不涉及**沙箱文件操作时选用：

- 纯聊天、日常对话
- 概念解释、知识问答（不依赖实时外部数据，或依赖 MCP/数据集工具）
- 文本翻译、润色、改写
- 写作、创意生成
- 逻辑推理、数学计算（无需外部工具）
- 对**已有文本**进行总结、归纳
- 含相对时间的业务分析（如「今年第一季度运行情况并与去年同期对比」）

显式询问「现在几点」「今天几号」应使用 `datetime` skill，而非本 skill。

### 回答要求
- 使用清晰、准确的回答（使用用户提问相同的语言回答，除非有特别要求）
- 信息不足时明确说明，禁止编造事实
- 含相对时间时，禁止臆造当前年份或区间
- 回答内容应直接、有用，避免无关赘述
```

- [ ] **Step 2: Update datetime SKILL.md**

在 `backend/app/agent/skills/datetime/SKILL.md` 的「## 何时使用」段落后追加一段：

```markdown
**相对时间业务句**（如「今年第一季度」「去年同期」嵌入风电场/营收分析）由 executor 全局预注入系统时间并合并本工具，Planner **无需**单独拆 `datetime` 步；仍由业务 skill（如 `general`）一步完成。
```

- [ ] **Step 3: Update planner examples**

在 `backend/app/agent/graphs/nodes/planner.py` 的 `PLANNER_SYSTEM_TEMPLATE` 中：

1. 将第 32 行改为更精确表述：

```python
不要把需要「当前服务器时间/日期」的显式问答（几点、几号、星期几）分给 general；含「今年/去年同期」等业务相对时间的分析仍可分给 general（executor 会自动锚定日期）。不要把「列出/读取/写入沙箱文件」分给 general（应选 file）。
```

2. 在 `## 示例` 区块末尾（`把这份 PDF 转成幻灯片` 示例之后）增加：

```python
用户：桂山风电场今年第一季度运行情况并与去年同期对比 → steps: [{{"id":"s1","skill_id":"general","goal":"桂山风电场今年第一季度运行情况并与去年同期对比"}}]
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/skills/general/SKILL.md backend/app/agent/skills/datetime/SKILL.md backend/app/agent/graphs/nodes/planner.py
git commit -m "docs(agent): update skill docs and planner for temporal anchor"
```

---

### Task 7: 手动验证

**Files:** none

- [ ] **Step 1: Run all new tests**

Run: `cd backend && python -m pytest tests/test_datetime_tool.py tests/test_temporal_context.py tests/test_executor_temporal.py -v`

Expected: all passed

- [ ] **Step 2: Manual agent smoke test**

1. 启动 backend（`uvicorn` 或项目既有脚本）。
2. 在 Agent 对话输入：`请对桂山风电场今年第一季度运行情况分析，并与去年同期对比`
3. 确认：
   - Plan 为单步 `general`（无单独 `datetime` 步）
   - Subagent 轨迹或日志中可见 `get_system_datetime` 在工具列表，或回复中区间年份与服务器当前年一致（如 2026 vs 2025）

- [ ] **Step 3: Update spec status (optional)**

在 `docs/superpowers/specs/2026-06-29-general-skill-temporal-anchor-design.md` 将 **状态** 改为「已实现」，并追加 §12 实现对照表（文件路径与 commit hash）。

```bash
git add docs/superpowers/specs/2026-06-29-general-skill-temporal-anchor-design.md
git commit -m "docs: mark temporal anchor spec as implemented"
```

---

## Spec coverage checklist

| Spec § | Task |
|--------|------|
| §1.2 按需触发 + 全局 + 双保险 | Task 2, 5 |
| §4.1 temporal_context 模块 | Task 2 |
| §4.2 词表 | Task 2 |
| §4.3 datetime_tool 共享 | Task 1 |
| §5 Executor 改动 | Task 3, 4, 5 |
| §5.2 goal_override | Task 4 |
| §6 SKILL / Planner | Task 6 |
| §8 测试 | Task 1–3, 7 |
| §9 边界（去重、多步同一 user_message） | Task 2 `prepare_executor_temporal_context`, Task 3 dedupe test |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-29-general-skill-temporal-anchor.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做代码审查，迭代快
2. **Inline Execution** — 在本会话按 Task 顺序直接实现，批次间设检查点

你希望用哪种方式开始实现？
