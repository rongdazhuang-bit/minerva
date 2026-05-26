# Agent 思考过程采集与展示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec 实现 Agent v2 主动开启思考模式、Planner/Subagent/Synthesizer 思考文本双写持久化、SSE v2 扩展，以及前端独立思考折叠区（默认关、输出完成后自动折叠）。

**Architecture:** 统一 `resolve_agent_thinking_config` + `ChatModelFactory` 注入 `extra_body`；`ReasoningCollector` 挂 `GraphDeps` 负责内存分段、SSE 推送与 Run 结束 message 聚合；各 LLM 节点在 `llm.round` 写入 `reasoning_text`；`memory.persist` 不改动。前端将运行过程与思考过程拆为两个 Collapse。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async, PostgreSQL, LangChain/LangGraph, pytest, React/minerva-ui, Ant Design, i18next

**Spec:** `docs/superpowers/specs/2026-05-26-agent-reasoning-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

**环境变量:** 新增 `AGENT_ENABLE_THINKING` 时同步 `backend/.env.example` 与 `backend/.env.dev`（见 minerva-conventions）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/agent/infrastructure/thinking_config.py` | **新建** 思考开关优先级解析 |
| `backend/app/config.py` | `agent_enable_thinking` |
| `backend/.env.example` / `backend/.env.dev` | `AGENT_ENABLE_THINKING=false` |
| `backend/sql/patches/2026-05-26-agent-reasoning.sql` | **新建** DDL |
| `backend/sql/schema_postgresql.sql` | 同步列 |
| `backend/app/agent/domain/db/models.py` | ORM `reasoning_text` |
| `backend/app/agent/infrastructure/repository.py` | `append_agent_message` / `update_run_node_reasoning_text` |
| `backend/app/agent/infrastructure/reasoning_collector.py` | **新建** 分段采集 + SSE |
| `backend/app/agent/infrastructure/chat_model_factory.py` | 注入 `extra_body` |
| `backend/app/agent/infrastructure/usage_tracker.py` | `llm.round` 后更新 reasoning |
| `backend/app/agent/infrastructure/event_mapper.py` | reasoning delta 带 phase |
| `backend/app/agent/domain/sse_v2.py` | 新事件枚举 |
| `backend/app/agent/graphs/deps.py` | 挂 `ReasoningCollector` |
| `backend/app/agent/graphs/nodes/planner.py` | 采集 planner reasoning |
| `backend/app/agent/graphs/nodes/subagent_runner.py` | 绑定 phase/step + finalize |
| `backend/app/agent/graphs/nodes/synthesizer.py` | 流式 reasoning + finalize |
| `backend/app/agent/service/agent_graph_run_service.py` | Run 入参 + message 双写 |
| `backend/app/agent/api/v2/schemas.py` | `enable_thinking` / message reasoning 字段 |
| `backend/app/agent/api/v2/router.py` | 映射 API 字段 |
| `backend/tests/test_agent_thinking_config.py` | **新建** |
| `backend/tests/test_agent_reasoning_collector.py` | **新建** |
| `backend/tests/test_agent_event_mapper.py` | **新建** |
| `backend/tests/test_agent_chat_model_factory.py` | 扩展 extra_body 测试 |
| `minerva-ui/src/api/agent.ts` | Run body + message types |
| `minerva-ui/src/api/agent-stream-v2.ts` | 新 SSE 类型 / trace 格式化 |
| `minerva-ui/src/features/agent/agentSkillUi.ts` | `reasoningSegments` 类型与映射 |
| `minerva-ui/src/features/agent/AgentsPage.tsx` | Switch + 双 Collapse |
| `minerva-ui/src/features/agent/AgentsPage.css` | 思考区样式微调 |
| `minerva-ui/src/i18n/locales/zh-CN.json` / `en.json` | `agents.thinkingMode` 等 |
| `docs/agent-module-design.md` | § SSE / 持久化回填 |
| `docs/superpowers/specs/2026-05-26-agent-reasoning-design.md` | 状态改为已实现 |

**不修改:** `memory_persist_service.py`、`memory_extract_llm.py`（保持现状，不带思考）。

---

### Task 1: 思考开关解析 + 配置

**Files:**
- Create: `backend/app/agent/infrastructure/thinking_config.py`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`, `backend/.env.dev`
- Create: `backend/tests/test_agent_thinking_config.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_agent_thinking_config.py
from types import SimpleNamespace

from app.agent.infrastructure.thinking_config import resolve_agent_thinking_config


def test_run_flag_overrides_model_and_env():
    settings = SimpleNamespace(agent_enable_thinking=True)
    cfg = resolve_agent_thinking_config(
        run_flag=False,
        model_config_raw='{"enable_thinking": true, "thinking_budget": 4096}',
        settings=settings,
    )
    assert cfg.enabled is False
    assert cfg.extra_body == {}


def test_model_config_used_when_run_flag_none():
    settings = SimpleNamespace(agent_enable_thinking=False)
    cfg = resolve_agent_thinking_config(
        run_flag=None,
        model_config_raw='{"enable_thinking": true, "reasoning_effort": "medium"}',
        settings=settings,
    )
    assert cfg.enabled is True
    assert cfg.extra_body["enable_thinking"] is True
    assert cfg.extra_body["reasoning_effort"] == "medium"


def test_env_default_when_no_run_and_empty_model_config():
    settings = SimpleNamespace(agent_enable_thinking=True)
    cfg = resolve_agent_thinking_config(
        run_flag=None,
        model_config_raw=None,
        settings=settings,
    )
    assert cfg.enabled is True
    assert cfg.extra_body == {"enable_thinking": True}
```

- [ ] **Step 2: 运行测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_agent_thinking_config.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `thinking_config.py`**

```python
# backend/app/agent/infrastructure/thinking_config.py
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

log = logging.getLogger(__name__)

_THINKING_KEYS = frozenset({"enable_thinking", "thinking_budget", "reasoning_effort"})


@dataclass(frozen=True)
class ThinkingConfig:
    """Resolved thinking-mode settings for one agent run."""

    enabled: bool
    extra_body: dict[str, Any]


def _parse_model_config(raw: str | None) -> dict[str, Any]:
    if not raw or not str(raw).strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        log.debug("agent thinking model_config JSON invalid: %s", exc)
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _thinking_extra_body(model_cfg: dict[str, Any], *, enabled: bool) -> dict[str, Any]:
    if not enabled:
        return {}
    out: dict[str, Any] = {}
    for key in _THINKING_KEYS:
        if key in model_cfg:
            out[key] = model_cfg[key]
    if "enable_thinking" not in out:
        out["enable_thinking"] = True
    return out


def resolve_agent_thinking_config(
    *,
    run_flag: bool | None,
    model_config_raw: str | None,
    settings: Any,
) -> ThinkingConfig:
    """Resolve thinking switch: run request > sys_models.model_config > AGENT_ENABLE_THINKING."""

    model_cfg = _parse_model_config(model_config_raw)
    if run_flag is not None:
        enabled = bool(run_flag)
    elif "enable_thinking" in model_cfg:
        enabled = bool(model_cfg["enable_thinking"])
    else:
        enabled = bool(getattr(settings, "agent_enable_thinking", False))
    return ThinkingConfig(enabled=enabled, extra_body=_thinking_extra_body(model_cfg, enabled=enabled))
```

- [ ] **Step 4: 在 `config.py` 增加字段**

```python
    agent_enable_thinking: bool = Field(
        default=False,
        description="Agent 默认是否向上游请求思考模式（Run 与 model_config 可覆盖）。",
        validation_alias=AliasChoices("AGENT_ENABLE_THINKING", "agent_enable_thinking"),
    )
```

并在 `backend/.env.example` / `backend/.env.dev` 追加：

```env
AGENT_ENABLE_THINKING=false
```

- [ ] **Step 5: 运行测试确认 PASS**

Run: `cd backend && python -m pytest tests/test_agent_thinking_config.py -v`

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/infrastructure/thinking_config.py backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_agent_thinking_config.py
git commit -m "feat(agent): add thinking config resolver with priority cascade"
```

---

### Task 2: 数据库迁移与 ORM

**Files:**
- Create: `backend/sql/patches/2026-05-26-agent-reasoning.sql`
- Modify: `backend/sql/schema_postgresql.sql`
- Modify: `backend/app/agent/domain/db/models.py`

- [ ] **Step 1: 编写 patch SQL**

```sql
-- backend/sql/patches/2026-05-26-agent-reasoning.sql
ALTER TABLE public.agent_run_node
  ADD COLUMN IF NOT EXISTS reasoning_text text NULL;

COMMENT ON COLUMN public.agent_run_node.reasoning_text IS '该 llm.round 节点 LLM 调用的思考全文';

ALTER TABLE public.agent_message
  ADD COLUMN IF NOT EXISTS reasoning_text text NULL;

COMMENT ON COLUMN public.agent_message.reasoning_text IS '助手消息对应的思考合并纯文本';
```

- [ ] **Step 2: 同步 `schema_postgresql.sql`**

在 `agent_run_node`、`agent_message` 表定义中各追加 `reasoning_text text NULL` 及 COMMENT。

- [ ] **Step 3: ORM 字段**

`AgentRunNode` 与 `AgentMessage` 各增加：

```python
    reasoning_text: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 4: 本地执行 patch（开发库）**

Run: `psql "$DATABASE_URL" -f backend/sql/patches/2026-05-26-agent-reasoning.sql`  
Expected: `ALTER TABLE` 成功

- [ ] **Step 5: Commit**

```bash
git add backend/sql/patches/2026-05-26-agent-reasoning.sql backend/sql/schema_postgresql.sql backend/app/agent/domain/db/models.py
git commit -m "feat(agent): add reasoning_text columns for run nodes and messages"
```

---

### Task 3: ReasoningCollector + SSE 事件类型

**Files:**
- Create: `backend/app/agent/infrastructure/reasoning_collector.py`
- Modify: `backend/app/agent/domain/sse_v2.py`
- Create: `backend/tests/test_agent_reasoning_collector.py`

- [ ] **Step 1: 扩展 SSE 枚举**

在 `AgentSseEventType` 追加：

```python
    llm_reasoning_segment_done = "llm.reasoning.segment_done"
    llm_reasoning_done = "llm.reasoning.done"
```

- [ ] **Step 2: 写 collector 测试**

```python
# backend/tests/test_agent_reasoning_collector.py
import uuid
from unittest.mock import AsyncMock

import pytest

from app.agent.infrastructure.reasoning_collector import ReasoningCollector


@pytest.mark.asyncio
async def test_collector_emits_delta_and_segment_done():
    emitted: list[bytes] = []

    async def emit_sse(line: bytes) -> None:
        emitted.append(line)

    collector = ReasoningCollector(
        run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        emit_sse=emit_sse,
        thinking_enabled=True,
    )
    await collector.append_delta(
        "planner",
        "think-a",
        step_id=None,
        skill_id=None,
    )
    await collector.finalize_segment(
        "planner",
        reasoning_tokens=3,
        step_id=None,
        skill_id=None,
    )
    payload = collector.build_message_reasoning()
    assert payload["segments"][0]["text"] == "think-a"
    assert payload["reasoning_tokens"] == 3
    assert len(emitted) >= 2


def test_collector_noop_when_thinking_disabled():
    collector = ReasoningCollector(
        run_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
        emit_sse=None,
        thinking_enabled=False,
    )
    assert collector.build_message_reasoning() is None
    assert collector.build_message_reasoning_text() is None
```

- [ ] **Step 3: 实现 `reasoning_collector.py`**

核心逻辑：

- `_segment_key(phase, step_id, skill_id) -> tuple`
- `append_delta`：thinking_enabled 时累积文本 + `build_sse_event(llm_delta, channel=reasoning, phase, ...)`
- `finalize_segment`：写 segment `reasoning_tokens` + 发 `llm.reasoning.segment_done`
- `mark_all_done`：发 `llm.reasoning.done`（payload 含合计 `reasoning_tokens`）
- `build_message_reasoning()` → `{"segments": [...], "reasoning_tokens": N}` 或 `None`
- `build_message_reasoning_text()` → 合并文本（每段前缀 `[Planner]` / `[file · s1]` / `[Synthesizer]`）

可见 phase 白名单：`planner`, `subagent`, `synthesizer`

- [ ] **Step 4: 运行测试**

Run: `cd backend && python -m pytest tests/test_agent_reasoning_collector.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/reasoning_collector.py backend/app/agent/domain/sse_v2.py backend/tests/test_agent_reasoning_collector.py
git commit -m "feat(agent): add ReasoningCollector and reasoning SSE event types"
```

---

### Task 4: ChatModelFactory 注入 extra_body

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/tests/test_agent_chat_model_factory.py`

- [ ] **Step 1: 写测试**

```python
def test_chat_model_factory_injects_extra_body_when_thinking_enabled(monkeypatch):
    captured = {}

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setattr("app.agent.infrastructure.chat_model_factory.ChatOpenAI", FakeChatOpenAI)
    from app.agent.infrastructure.thinking_config import ThinkingConfig

    row, workspace_id = _model_row()
    ChatModelFactory.from_sys_model_row(
        row,
        workspace_id=workspace_id,
        thinking=ThinkingConfig(enabled=True, extra_body={"enable_thinking": True, "thinking_budget": 8192}),
    )
    assert captured["model_kwargs"]["extra_body"]["enable_thinking"] is True
    assert captured["model_kwargs"]["extra_body"]["thinking_budget"] == 8192
```

- [ ] **Step 2: 修改 factory**

```python
from app.agent.infrastructure.thinking_config import ThinkingConfig

# signature 增加 thinking: ThinkingConfig | None = None
if thinking and thinking.enabled and thinking.extra_body:
    kwargs["model_kwargs"] = {"extra_body": dict(thinking.extra_body)}
```

- [ ] **Step 3: 运行测试**

Run: `cd backend && python -m pytest tests/test_agent_chat_model_factory.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/infrastructure/chat_model_factory.py backend/tests/test_agent_chat_model_factory.py
git commit -m "feat(agent): inject thinking extra_body in ChatModelFactory"
```

---

### Task 5: Repository 与 usage_tracker 写 reasoning_text

**Files:**
- Modify: `backend/app/agent/infrastructure/repository.py`
- Modify: `backend/app/agent/infrastructure/usage_tracker.py`

- [ ] **Step 1: `append_agent_message` 增加参数**

```python
async def append_agent_message(..., reasoning_text: str | None = None) -> AgentMessage:
    row = AgentMessage(..., reasoning_text=reasoning_text, ...)
```

- [ ] **Step 2: 新增 `update_run_node_reasoning_text`**

```python
async def update_run_node_reasoning_text(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    reasoning_text: str | None,
) -> None:
    row = await session.get(AgentRunNode, node_id)
    if row is None:
        return
    row.reasoning_text = reasoning_text
    await session.flush()
```

- [ ] **Step 3: `record_llm_call` 增加可选 `reasoning_text`**

在 `insert_run_node` 时传入 `reasoning_text=reasoning_text`（扩展 `insert_run_node` 签名），或 insert 后立即 `update_run_node_reasoning_text`。

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/infrastructure/repository.py backend/app/agent/infrastructure/usage_tracker.py
git commit -m "feat(agent): persist reasoning_text on llm.round and assistant messages"
```

---

### Task 6: GraphDeps 集成 ReasoningCollector

**Files:**
- Modify: `backend/app/agent/graphs/deps.py`
- Modify: `backend/app/agent/service/agent_graph_run_service.py`

- [ ] **Step 1: `GraphDeps` 增加字段**

```python
from app.agent.infrastructure.reasoning_collector import ReasoningCollector

@dataclass
class GraphDeps:
    ...
    reasoning_collector: ReasoningCollector | None = None
```

- [ ] **Step 2: Run 入口解析 thinking 并构造 collector**

在 `agent_graph_run_service` 创建 model 前：

```python
from app.agent.infrastructure.thinking_config import resolve_agent_thinking_config

thinking = resolve_agent_thinking_config(
    run_flag=enable_thinking,
    model_config_raw=sys_row.model_config if sys_row else None,
    settings=settings,
)
model_row = await ChatModelFactory.get(..., thinking=thinking)

reasoning_collector = ReasoningCollector(
    run_id=run_id,
    session_id=session_id,
    emit_sse=emit,
    thinking_enabled=thinking.enabled,
)
deps = GraphDeps(..., reasoning_collector=reasoning_collector)
```

- [ ] **Step 3: `AgentRunCreateV2` + router 传入 `enable_thinking`**

`schemas.py`:

```python
    enable_thinking: bool | None = Field(default=None, description="是否开启思考模式；null 表示按 model_config / 全局默认。")
```

router 解构并传入 service。

- [ ] **Step 4: Run 成功写 message 时双写**

```python
reasoning_meta = deps.reasoning_collector.build_message_reasoning() if deps.reasoning_collector else None
reasoning_text = deps.reasoning_collector.build_message_reasoning_text() if deps.reasoning_collector else None
meta = {"usage": usage_snapshot} if usage_snapshot else {}
if reasoning_meta:
    meta["reasoning"] = reasoning_meta
await agent_repo.append_agent_message(
    ...,
    meta_json=meta or None,
    reasoning_text=reasoning_text,
)
```

Run 结束前调用 `await deps.reasoning_collector.mark_all_done()`（在 synthesizer 完成后、写 message 前）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graphs/deps.py backend/app/agent/service/agent_graph_run_service.py backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/router.py
git commit -m "feat(agent): wire thinking config and ReasoningCollector into graph runs"
```

---

### Task 7: Planner / Subagent / Synthesizer 采集

**Files:**
- Modify: `backend/app/agent/graphs/nodes/planner.py`
- Modify: `backend/app/agent/infrastructure/event_mapper.py`
- Modify: `backend/app/agent/graphs/nodes/subagent_runner.py`
- Modify: `backend/app/agent/graphs/nodes/synthesizer.py`
- Create: `backend/tests/test_agent_event_mapper.py`

- [ ] **Step 1: 辅助函数提取 reasoning 文本**

新建或放在 `reasoning_collector.py`：

```python
def extract_reasoning_from_langchain_message(msg: Any) -> str:
    kwargs = getattr(msg, "additional_kwargs", None) or {}
    for key in ("reasoning_content", "reasoning"):
        val = kwargs.get(key)
        if val:
            return str(val)
    return ""
```

- [ ] **Step 2: Planner — raw 消息后采集**

```python
if raw_msg is not None and deps.reasoning_collector:
    text = extract_reasoning_from_langchain_message(raw_msg)
    if text:
        await deps.reasoning_collector.append_delta("planner", text)
    tokens = usage_document_flat(extract_usage_document(raw_msg)).get("details", {}).get("reasoning_tokens", 0)
    await deps.reasoning_collector.finalize_segment("planner", reasoning_tokens=int(tokens or 0))
    # record_llm_call 后 update_run_node_reasoning_text(node_id, text)
```

- [ ] **Step 3: event_mapper — delta 带 phase**

扩展 `map_langchain_stream_event` 签名增加 `phase`, `step_id`, `skill_id`；reasoning payload 带上这些字段。

- [ ] **Step 4: subagent_runner**

在 `on_chat_model_stream` 经 mapper 之前，若 collector 存在，同步 `append_delta("subagent", ...)`。

在 `on_chat_model_end`：

```python
text = extract_reasoning_from_langchain_message(data.get("output"))
node_id = await deps.record_llm_call_to_db(...)
if node_id and text:
    await agent_repo.update_run_node_reasoning_text(deps.db, node_id=node_id, reasoning_text=text)
await deps.reasoning_collector.finalize_segment("subagent", reasoning_tokens=..., step_id=step.id, skill_id=step.skill_id)
```

- [ ] **Step 5: synthesizer `_stream_model_text`**

流式循环内：

```python
reasoning_piece = extract_reasoning_from_chunk(chunk)  # additional_kwargs
if reasoning_piece and deps.reasoning_collector:
    await deps.reasoning_collector.append_delta("synthesizer", reasoning_piece)
# content 仍走 assistant channel
```

结束后 `finalize_segment("synthesizer", ...)` + 写 `llm.round.reasoning_text`。

- [ ] **Step 6: event_mapper 测试**

```python
def test_map_reasoning_delta_includes_phase():
    chunk = SimpleNamespace(content="", additional_kwargs={"reasoning_content": "r1"})
    event = {"event": "on_chat_model_stream", "data": {"chunk": chunk}}
    line = map_langchain_stream_event(event, run_id=uuid.uuid4(), session_id=uuid.uuid4(), phase="subagent", step_id="s1", skill_id="file")
    assert line is not None
    assert b'"channel": "reasoning"' in line
    assert b'"phase": "subagent"' in line
```

- [ ] **Step 7: 运行测试**

Run: `cd backend && python -m pytest tests/test_agent_event_mapper.py tests/test_agent_reasoning_collector.py -v`

- [ ] **Step 8: Commit**

```bash
git add backend/app/agent/graphs/nodes/planner.py backend/app/agent/infrastructure/event_mapper.py backend/app/agent/graphs/nodes/subagent_runner.py backend/app/agent/graphs/nodes/synthesizer.py backend/tests/test_agent_event_mapper.py
git commit -m "feat(agent): capture reasoning in planner, subagent, and synthesizer nodes"
```

---

### Task 8: HTTP API 返回 reasoning 字段

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`

- [ ] **Step 1: 扩展 `AgentMessageOut`**

```python
class AgentMessageReasoningOut(BaseModel):
    segments: list[dict[str, Any]]
    reasoning_tokens: int = Field(ge=0)

class AgentMessageOut(BaseModel):
    ...
    reasoning_text: str | None = None
    reasoning: AgentMessageReasoningOut | None = None
```

- [ ] **Step 2: router 映射**

从 `m.reasoning_text` 与 `m.meta_json.get("reasoning")` 填充。

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/router.py
git commit -m "feat(agent): expose reasoning fields on session message API"
```

---

### Task 9: 前端类型与 SSE 处理

**Files:**
- Modify: `minerva-ui/src/api/agent.ts`
- Modify: `minerva-ui/src/api/agent-stream-v2.ts`
- Modify: `minerva-ui/src/features/agent/agentSkillUi.ts`

- [ ] **Step 1: Run 请求体**

```typescript
export type AgentRunCreateBody = {
  ...
  enable_thinking?: boolean | null
}
```

- [ ] **Step 2: Message 类型**

```typescript
export type AgentMessageReasoning = {
  segments: Array<{
    phase: string
    step_id: string | null
    skill_id: string | null
    text: string
    reasoning_tokens: number
  }>
  reasoning_tokens: number
}
```

`AgentMessageOut` 增加 `reasoning_text?`, `reasoning?`。

- [ ] **Step 3: `AgentChatMsg` 扩展**

```typescript
export type AgentReasoningSegment = AgentMessageReasoning['segments'][number]

export type AgentChatMsg = {
  ...
  reasoningSegments?: AgentReasoningSegment[]
  reasoningTokens?: number
}
```

- [ ] **Step 4: `agentMessagesToChat` 映射**

从 `reasoning` / `reasoning_text` 填充；有 segments 时优先用 segments。

- [ ] **Step 5: `formatAgentV2TraceLine` 处理新事件**

- `llm.reasoning.segment_done` → 可选 trace 行（或跳过，思考区单独展示）
- `llm.reasoning.done` → 不进入 processLog

- [ ] **Step 6: Commit**

```bash
git add minerva-ui/src/api/agent.ts minerva-ui/src/api/agent-stream-v2.ts minerva-ui/src/features/agent/agentSkillUi.ts
git commit -m "feat(ui): agent types and SSE helpers for reasoning"
```

---

### Task 10: AgentsPage UI — Switch + 双 Collapse

**Files:**
- Modify: `minerva-ui/src/features/agent/AgentsPage.tsx`
- Modify: `minerva-ui/src/features/agent/AgentsPage.css`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1: 状态**

```typescript
const [thinkingEnabled, setThinkingEnabled] = useState(false) // 默认关
const [reasoningOpenKeys, setReasoningOpenKeys] = useState<string[]>([])
```

- [ ] **Step 2: 模型选择旁 Switch**

```tsx
<Switch
  checked={thinkingEnabled}
  onChange={setThinkingEnabled}
  size="small"
/>
<span>{t('agents.thinkingMode')}</span>
```

i18n:

- `agents.thinkingMode`: 「思考模式」/ `Thinking mode`
- `agents.reasoningTrace`: 「思考过程 · {{count}} tokens」/ `Reasoning · {{count}} tokens`

- [ ] **Step 3: Run 请求**

```typescript
enable_thinking: thinkingEnabled ? true : false,
```

（显式传 false 以覆盖 model_config / 全局；若希望「未触摸 Switch 时不覆盖」，可改为仅 true 时传 `enable_thinking: true` —— **本计划按 spec 默认关且显式 false 覆盖**。）

- [ ] **Step 4: SSE handler**

- `llm.delta` + `channel===reasoning`：按 `phase/step_id/skill_id` 更新 `reasoningSegments`；展开 `reasoningOpenKeys=['reasoning']`
- `llm.reasoning.segment_done`：更新对应 segment 的 `reasoning_tokens`
- `llm.reasoning.done`：更新 `reasoningTokens`；`setReasoningOpenKeys([])` 自动折叠
- `llm.delta` + `channel===assistant`：不再清空 trace keys 时误伤 reasoning（分离 `traceOpenKeys` 与 `reasoningOpenKeys`）

- [ ] **Step 5: 拆分 Collapse**

`assistantTraceBelowRobot` 拆为两个函数：

1. `processTraceCollapse` — 仅 `processLog`（label: `agents.assistantTrace`）
2. `reasoningTraceCollapse` — 仅 segments（label: `agents.reasoningTrace` with token count）

布局顺序：content → 运行过程 → 思考过程

无 `reasoningSegments` 且无流式 reasoning 时隐藏思考 Collapse。

- [ ] **Step 6: CSS**

`.agents-page__reasoning-trace` 容器；段标题 `.agents-page__reasoning-segment-label`；正文复用 `.agents-page__process-reasoning`。

- [ ] **Step 7: 手动验证**

1. 思考模式关 → 无思考 Collapse  
2. 思考模式开 + 推理模型 → 流式分段、token 数、完成后自动折叠  
3. 刷新会话 → 从 API 恢复思考内容  

- [ ] **Step 8: Commit**

```bash
git add minerva-ui/src/features/agent/AgentsPage.tsx minerva-ui/src/features/agent/AgentsPage.css minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
git commit -m "feat(ui): separate reasoning trace with thinking mode switch"
```

---

### Task 11: 文档回填

**Files:**
- Modify: `docs/agent-module-design.md`
- Modify: `docs/superpowers/specs/2026-05-26-agent-reasoning-design.md`

- [ ] **Step 1: 更新 spec 状态**

`状态：已实现（YYYY-MM-DD）` + 实现对照表（关键文件路径）。

- [ ] **Step 2: 更新 agent-module-design.md**

- § SSE 表增加 `llm.reasoning.segment_done`、`llm.reasoning.done`
- § 持久化增加 `reasoning_text` 列说明
- § 前端：运行过程 / 思考过程分离

- [ ] **Step 3: Commit**

```bash
git add docs/agent-module-design.md docs/superpowers/specs/2026-05-26-agent-reasoning-design.md
git commit -m "docs: agent reasoning design implementation notes"
```

---

## Spec coverage checklist

| Spec 要求 | Task |
|-----------|------|
| 开关优先级 前端 > model_config > env | Task 1, 6 |
| ChatModelFactory extra_body | Task 4 |
| agent_run_node.reasoning_text | Task 2, 5, 7 |
| agent_message 双写 | Task 2, 5, 6 |
| Memory 不带思考 | 明确不修改 |
| SSE llm.delta phase | Task 3, 7 |
| SSE segment_done / done | Task 3, 10 |
| 前端 Switch 默认关 | Task 10 |
| 双 Collapse + 自动折叠 | Task 10 |
| 会话恢复 | Task 8, 9 |

---

## 全量回归

Run: `cd backend && python -m pytest tests/test_agent_thinking_config.py tests/test_agent_reasoning_collector.py tests/test_agent_event_mapper.py tests/test_agent_chat_model_factory.py -v`

Run: `cd minerva-ui && npm run typecheck`（或项目等价命令）
