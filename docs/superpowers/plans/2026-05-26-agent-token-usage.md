# Agent Token 用量分层统计 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按 spec 实现 Agent v2 分层 token 统计：每次 LLM 调用持久化、主图节点 rollup、Run/Session `usage_json` 落库，并扩展 SSE/API；前端在助手消息复制按钮旁展示本轮 token，刷新后可从消息 `meta_json` 恢复。

**Architecture:** 混合式（spec 方案 3）：`RunUsageTracker` 挂在 `GraphDeps`，每次 LLM 调用写 `agent_run_node`（`llm.round`）并内存累计；节点边界 rollup 父节点；Run finalize 写分层 `usage_json` 并 merge Session；后台 `memory.persist` 二次 patch Run/Session/助手消息 meta。归一化与 merge 复用并扩展 `openai_usage.py`。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async, PostgreSQL JSONB, LangGraph/LangChain, pytest, React/frontend, i18next

**Spec:** `docs/superpowers/specs/2026-05-26-agent-token-usage-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

**已有部分实现（勿重复造轮子）:**
- `backend/app/agent/infrastructure/openai_usage.py` — `normalize_openai_usage` / `merge_openai_usage`
- `backend/app/agent/graphs/deps.py` — `emit_llm_usage` + flat `accumulated_usage`
- `frontend` — SSE 采集 + 复制按钮旁 `{{count}} tokens`（`AgentsPage.tsx`、`agent-stream-v2.ts`）

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/sql/patches/2026-05-26-agent-usage-json.sql` | 新增 `usage_json` 列 |
| `backend/sql/schema_postgresql.sql` | 同步建表脚本 |
| `backend/app/agent/domain/db/models.py` | ORM 字段 |
| `backend/app/agent/infrastructure/openai_usage.py` | `merge_usage_document`、`extract_usage_details` |
| `backend/app/agent/infrastructure/usage_tracker.py` | **新建** Run 内采集、rollup、快照 |
| `backend/app/agent/infrastructure/repository.py` | `update_run_node_usage`、`merge_run_usage_json`、`merge_session_usage_json`、`patch_assistant_message_usage_by_run` |
| `backend/app/agent/graphs/deps.py` | 委托 `RunUsageTracker`；扩展 `emit_llm_usage` |
| `backend/app/agent/graphs/nodes/planner.py` | planner LLM record + rollup |
| `backend/app/agent/graphs/nodes/subagent_runner.py` | `llm.round` per `on_chat_model_end` |
| `backend/app/agent/graphs/nodes/executor.py` | subagent rollup、`subagent.finished.step_usage` |
| `backend/app/agent/graphs/nodes/synthesizer.py` | synthesizer 节点 + record |
| `backend/app/agent/service/agent_graph_run_service.py` | 分层 finalize、Session merge、助手 `meta_json` |
| `backend/app/agent/service/memory_persist_service.py` | 后台 patch Run/Session/消息 |
| `backend/app/agent/api/v2/schemas.py` | `usage` 字段 |
| `backend/app/agent/api/v2/router.py` | 映射 `usage_json` → `usage` |
| `backend/tests/test_agent_openai_usage.py` | 扩展 merge 测试 |
| `backend/tests/test_agent_usage_tracker.py` | **新建** tracker 单测 |
| `backend/tests/test_agent_memory_persist_usage.py` | **新建** 后台 patch 单测 |
| `backend/tests/test_agent_session_usage_api.py` | **新建** API 测试 |
| `frontend/src/api/agent.ts` | Session 类型 `usage` |
| `frontend/src/features/agent/agentSkillUi.ts` | 从 message meta 解析 `totalTokens` |
| `frontend/src/features/agent/AgentsPage.tsx` | 加载会话时恢复 token；侧栏 session 累计（可选） |
| `docs/superpowers/specs/2026-05-26-agent-token-usage-design.md` | 状态 + 实现对照 |
| `docs/agent-module-design.md` | §7 / §9.2 回填 |

---

### Task 1: 数据库迁移与 ORM

**Files:**
- Create: `backend/sql/patches/2026-05-26-agent-usage-json.sql`
- Modify: `backend/sql/schema_postgresql.sql`（`agent_run_node`、`agent_session` 段）
- Modify: `backend/app/agent/domain/db/models.py`

- [ ] **Step 1: 编写 patch SQL**

```sql
-- backend/sql/patches/2026-05-26-agent-usage-json.sql
ALTER TABLE public.agent_run_node
  ADD COLUMN IF NOT EXISTS usage_json jsonb NULL;

COMMENT ON COLUMN public.agent_run_node.usage_json IS '该节点 LLM token 用量(JSONB，OpenAI 兼容 + 按需 details)';

ALTER TABLE public.agent_session
  ADD COLUMN IF NOT EXISTS usage_json jsonb NULL;

COMMENT ON COLUMN public.agent_session.usage_json IS '会话累计 token 用量(JSONB，含 by_phase)';
```

- [ ] **Step 2: 同步 `schema_postgresql.sql`**

在 `agent_run_node` 表定义中 `meta_json` 后追加：

```sql
  usage_json jsonb NULL,
```

在 `agent_session` 表定义中 `meta_json` 后追加：

```sql
  usage_json jsonb NULL,
```

并追加对应 `COMMENT ON COLUMN`。

- [ ] **Step 3: ORM 映射**

在 `AgentRunNode` 与 `AgentSession` 类中各增加：

```python
    usage_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 4: 本地验证 ORM 加载**

Run: `cd backend && python -c "from app.agent.domain.db.models import AgentRunNode, AgentSession; print(AgentRunNode.usage_json, AgentSession.usage_json)"`

Expected: 打印两个 SQLAlchemy 列描述，无 ImportError

- [ ] **Step 5: Commit**

```bash
git add backend/sql/patches/2026-05-26-agent-usage-json.sql backend/sql/schema_postgresql.sql backend/app/agent/domain/db/models.py
git commit -m "feat(agent): add usage_json columns for run nodes and sessions"
```

---

### Task 2: `merge_usage_document` 扩展

**Files:**
- Modify: `backend/app/agent/infrastructure/openai_usage.py`
- Modify: `backend/tests/test_agent_openai_usage.py`

- [ ] **Step 1: 写失败测试**

在 `test_agent_openai_usage.py` 末尾追加：

```python
from app.agent.infrastructure.openai_usage import merge_usage_document


def test_merge_usage_document_merges_by_phase_and_details() -> None:
    """Layered usage documents sum top-level, details, and by_phase buckets."""

    base = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "details": {"cached_tokens": 2},
        "by_phase": {
            "planner": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
    }
    delta = {
        "prompt_tokens": 3,
        "completion_tokens": 2,
        "total_tokens": 5,
        "details": {"cached_tokens": 1, "reasoning_tokens": 4},
        "by_phase": {
            "subagent": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "by_step": {
            "s1": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "skill_id": "file",
            },
        },
    }
    merged = merge_usage_document(base, delta)
    assert merged == {
        "prompt_tokens": 13,
        "completion_tokens": 7,
        "total_tokens": 20,
        "details": {"cached_tokens": 3, "reasoning_tokens": 4},
        "by_phase": {
            "planner": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            "subagent": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        },
        "by_step": {
            "s1": {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "total_tokens": 5,
                "skill_id": "file",
            },
        },
    }


def test_merge_usage_document_preserves_skill_id_on_step() -> None:
    """by_step merge keeps skill_id from the latest delta when present."""

    merged = merge_usage_document(
        {"by_step": {"s1": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2, "skill_id": "general"}}},
        {"by_step": {"s1": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3, "skill_id": "file"}}},
    )
    assert merged["by_step"]["s1"]["skill_id"] == "file"
    assert merged["by_step"]["s1"]["total_tokens"] == 5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_agent_openai_usage.py::test_merge_usage_document_merges_by_phase_and_details -v`

Expected: FAIL — `ImportError: cannot import name 'merge_usage_document'`

- [ ] **Step 3: 实现 `merge_usage_document`**

在 `openai_usage.py` 追加（保留现有函数不变）：

```python
UsageDocument = dict[str, Any]

_STANDARD_KEYS = ("prompt_tokens", "completion_tokens", "total_tokens")


def _merge_details(base: dict[str, Any] | None, delta: dict[str, Any] | None) -> dict[str, int] | None:
    """Sum numeric keys inside ``details``."""

    if not base and not delta:
        return None
    out: dict[str, int] = dict(base or {})
    for key, value in (delta or {}).items():
        n = _coerce_non_negative_int(value)
        if n is None:
            continue
        out[key] = int(out.get(key, 0)) + n
    return out or None


def _merge_usage_slice(base: OpenAIUsage | None, delta: OpenAIUsage | None) -> OpenAIUsage | None:
    """Merge one flat OpenAI usage object."""

    merged = merge_openai_usage(base, delta)
    return merged or None


def merge_usage_document(base: UsageDocument | None, delta: UsageDocument | None) -> UsageDocument:
    """Merge layered usage documents (top-level, details, by_phase, by_step)."""

    if not base and not delta:
        return {}
    out: UsageDocument = dict(base or {})
    if not delta:
        return out

    flat_delta = {k: delta[k] for k in _STANDARD_KEYS if k in delta}
    flat_base = {k: out[k] for k in _STANDARD_KEYS if k in out}
    flat_merged = merge_openai_usage(flat_base, flat_delta)
    for key in _STANDARD_KEYS:
        if key in flat_merged:
            out[key] = flat_merged[key]

    details = _merge_details(
        out.get("details") if isinstance(out.get("details"), dict) else None,
        delta.get("details") if isinstance(delta.get("details"), dict) else None,
    )
    if details:
        out["details"] = details

    for bucket in ("by_phase", "by_step"):
        base_bucket = out.get(bucket) if isinstance(out.get(bucket), dict) else {}
        delta_bucket = delta.get(bucket) if isinstance(delta.get(bucket), dict) else {}
        merged_bucket: dict[str, Any] = dict(base_bucket)
        for name, slice_delta in delta_bucket.items():
            if not isinstance(slice_delta, dict):
                continue
            prev = merged_bucket.get(name) if isinstance(merged_bucket.get(name), dict) else {}
            merged_slice = dict(prev)
            merged_slice.update(_merge_usage_slice(prev, slice_delta) or {})
            if "skill_id" in slice_delta:
                merged_slice["skill_id"] = slice_delta["skill_id"]
            merged_bucket[name] = merged_slice
        if merged_bucket:
            out[bucket] = merged_bucket

    return out


def build_phase_delta(phase: str, usage: OpenAIUsage) -> UsageDocument:
    """Wrap one LLM call usage into a document increment for ``by_phase``."""

    doc: UsageDocument = dict(usage)
    doc["by_phase"] = {phase: dict(usage)}
    return doc


def build_step_delta(step_id: str, skill_id: str, usage: OpenAIUsage) -> UsageDocument:
    """Wrap one step increment for ``by_step``."""

    return {
        **_merge_usage_slice({}, usage) or {},
        "by_step": {
            step_id: {
                **dict(usage),
                "skill_id": skill_id,
            }
        },
    }
```

- [ ] **Step 4: 运行全部 openai_usage 测试**

Run: `cd backend && pytest tests/test_agent_openai_usage.py -v`

Expected: 全部 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/openai_usage.py backend/tests/test_agent_openai_usage.py
git commit -m "feat(agent): add merge_usage_document for layered token stats"
```

---

### Task 3: `RunUsageTracker`

**Files:**
- Create: `backend/app/agent/infrastructure/usage_tracker.py`
- Create: `backend/tests/test_agent_usage_tracker.py`

- [ ] **Step 1: 写失败测试**

```python
"""Tests for RunUsageTracker in-memory aggregation."""

from __future__ import annotations

import uuid

import pytest

from app.agent.infrastructure.usage_tracker import RunUsageTracker


def test_tracker_accumulates_phase_and_builds_snapshot() -> None:
    """Tracker merges planner then subagent into run snapshot."""

    tracker = RunUsageTracker()
    tracker.record_call(
        {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        phase="planner",
    )
    tracker.record_call(
        {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6},
        phase="subagent",
        step_id="s1",
        skill_id="file",
    )
    snap = tracker.build_run_snapshot()
    assert snap["total_tokens"] == 21
    assert snap["by_phase"]["planner"]["total_tokens"] == 15
    assert snap["by_phase"]["subagent"]["total_tokens"] == 6
    assert snap["by_step"]["s1"]["skill_id"] == "file"


@pytest.mark.asyncio
async def test_tracker_record_llm_call_persists_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """record_llm_call writes llm.round node via repository hook."""

    inserted: list[dict] = []

    async def fake_insert(session, **kwargs):
        inserted.append(kwargs)
        row = type("Row", (), {"id": kwargs["node_id"]})()
        return row

    monkeypatch.setattr(
        "app.agent.infrastructure.repository.insert_run_node",
        fake_insert,
    )

    tracker = RunUsageTracker()
    run_id = uuid.uuid4()
    parent_id = uuid.uuid4()
    node_id = await tracker.record_llm_call(
        session=object(),
        run_id=run_id,
        parent_node_id=parent_id,
        sequence_idx=1,
        raw_usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        phase="subagent",
        step_id="s1",
        skill_id="general",
    )
    assert node_id is not None
    assert inserted[0]["node_type"] == "llm.round"
    assert inserted[0]["usage_json"]["total_tokens"] == 2
    assert inserted[0]["meta_json"]["phase"] == "subagent"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_agent_usage_tracker.py -v`

Expected: FAIL — module not found

- [ ] **Step 3: 实现 `usage_tracker.py`**

```python
"""Track layered LLM token usage for one agent run."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.openai_usage import (
    OpenAIUsage,
    UsageDocument,
    build_phase_delta,
    build_step_delta,
    extract_usage_from_langchain_output,
    merge_openai_usage,
    merge_usage_document,
    normalize_openai_usage,
)


@dataclass
class RunUsageTracker:
    """In-memory layered usage for a single run; optional DB persistence for llm.round."""

    document: UsageDocument = field(default_factory=dict)
    flat_total: OpenAIUsage = field(default_factory=dict)

    def _normalize_raw(self, raw_usage: Any) -> OpenAIUsage | None:
        """Normalize LangChain/OpenAI usage payload."""

        usage = normalize_openai_usage(raw_usage)
        if usage:
            return usage
        return extract_usage_from_langchain_output(raw_usage)

    def record_call(
        self,
        raw_usage: Any,
        *,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> OpenAIUsage | None:
        """Merge one LLM call into memory (no DB)."""

        usage = self._normalize_raw(raw_usage)
        if not usage:
            return None
        self.flat_total = merge_openai_usage(self.flat_total, usage)
        delta = build_phase_delta(phase, usage)
        if step_id and skill_id:
            delta = merge_usage_document(delta, build_step_delta(step_id, skill_id, usage))
        self.document = merge_usage_document(self.document, delta)
        return usage

    async def record_llm_call(
        self,
        session: AsyncSession,
        *,
        run_id: uuid.UUID,
        parent_node_id: uuid.UUID | None,
        sequence_idx: int,
        raw_usage: Any,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> uuid.UUID | None:
        """Persist ``llm.round`` and merge into memory."""

        usage = self.record_call(
            raw_usage,
            phase=phase,
            step_id=step_id,
            skill_id=skill_id,
        )
        if not usage:
            return None
        node_id = uuid.uuid4()
        meta: dict[str, Any] = {"phase": phase}
        if step_id is not None:
            meta["step_id"] = step_id
        if skill_id is not None:
            meta["skill_id"] = skill_id
        await agent_repo.insert_run_node(
            session,
            node_id=node_id,
            run_id=run_id,
            parent_node_id=parent_node_id,
            sequence_idx=sequence_idx,
            node_type="llm.round",
            node_name=phase,
            status="success",
            usage_json=dict(usage),
            meta_json=meta,
        )
        return node_id

    async def rollup_children(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        child_usage: OpenAIUsage,
    ) -> None:
        """Write rollup usage onto an existing parent node."""

        await agent_repo.update_run_node_usage(
            session,
            node_id=node_id,
            usage_json=dict(child_usage),
        )

    def build_run_snapshot(self) -> UsageDocument:
        """Return full run document for ``agent_run.usage_json``."""

        return dict(self.document)

    def build_session_delta(self) -> UsageDocument:
        """Return session merge delta (no by_step)."""

        snap = self.build_run_snapshot()
        out = {k: v for k, v in snap.items() if k != "by_step"}
        return out
```

- [ ] **Step 4: 在 `repository.py` 先加 stub（Task 4 完整实现，此处最小可编译）**

```python
async def update_run_node_usage(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    usage_json: dict[str, Any] | list[Any],
) -> None:
    """Update ``usage_json`` on one run node."""

    row = await session.get(AgentRunNode, node_id)
    if row is None:
        return
    row.usage_json = usage_json
    await session.flush()
```

并在 `insert_run_node` 签名中增加 `usage_json: dict[str, Any] | list[Any] | None = None`，构造 `AgentRunNode` 时传入。

- [ ] **Step 5: 运行 tracker 测试**

Run: `cd backend && pytest tests/test_agent_usage_tracker.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/infrastructure/usage_tracker.py backend/app/agent/infrastructure/repository.py backend/tests/test_agent_usage_tracker.py
git commit -m "feat(agent): add RunUsageTracker for layered token accounting"
```

---

### Task 4: Repository — Session/Run merge 与消息 patch

**Files:**
- Modify: `backend/app/agent/infrastructure/repository.py`
- Modify: `backend/tests/test_agent_usage_tracker.py`（如需）

- [ ] **Step 1: 扩展 `insert_run_node` 支持 `usage_json`**（若 Task 3 未完整合并）

- [ ] **Step 2: 追加 repository 函数**

```python
async def merge_run_usage_json(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    delta: dict[str, Any],
) -> None:
    """Merge layered usage into ``agent_run.usage_json``."""

    from app.agent.infrastructure.openai_usage import merge_usage_document

    row = await session.get(AgentRun, run_id)
    if row is None:
        return
    base = row.usage_json if isinstance(row.usage_json, dict) else {}
    row.usage_json = merge_usage_document(base, delta)
    await session.flush()


async def merge_session_usage_json(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    delta: dict[str, Any],
) -> None:
    """Merge run delta into ``agent_session.usage_json`` (drops by_step)."""

    from app.agent.infrastructure.openai_usage import merge_usage_document

    row = await session.get(AgentSession, session_id)
    if row is None:
        return
    base = row.usage_json if isinstance(row.usage_json, dict) else {}
    clean_delta = {k: v for k, v in delta.items() if k != "by_step"}
    row.usage_json = merge_usage_document(base, clean_delta)
    await session.flush()


async def patch_assistant_message_usage_by_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    usage_json: dict[str, Any],
) -> None:
    """Patch assistant message meta for one run (for UI reload)."""

    stmt = (
        select(AgentMessage)
        .where(AgentMessage.run_id == run_id, AgentMessage.role == "assistant")
        .order_by(AgentMessage.seq.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    meta = dict(row.meta_json) if isinstance(row.meta_json, dict) else {}
    meta["usage"] = usage_json
    row.meta_json = meta
    await session.flush()
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/infrastructure/repository.py
git commit -m "feat(agent): add usage merge helpers for run, session, and messages"
```

---

### Task 5: 集成 `GraphDeps` 与 SSE

**Files:**
- Modify: `backend/app/agent/graphs/deps.py`

- [ ] **Step 1: 在 `GraphDeps` 增加 tracker 与 llm.round 序号状态**

```python
from app.agent.infrastructure.usage_tracker import RunUsageTracker

@dataclass
class GraphDeps:
    ...
    usage_tracker: RunUsageTracker = field(default_factory=RunUsageTracker)
    _llm_round_seq: dict[uuid.UUID, int] = field(default_factory=dict)

    def next_llm_round_seq(self, parent_node_id: uuid.UUID) -> int:
        """Return next sequence index for ``llm.round`` under a parent node."""

        n = self._llm_round_seq.get(parent_node_id, 0)
        self._llm_round_seq[parent_node_id] = n + 1
        return n
```

- [ ] **Step 2: 重写 `emit_llm_usage` 委托 tracker + 保留 SSE**

逻辑顺序：
1. `usage = self.usage_tracker.record_call(...)` — 若 None 则 return
2. `self.accumulated_usage = self.usage_tracker.flat_total`（兼容旧字段）
3. SSE payload 增加 `node_id` 可选（若调用方传入）
4. `total_usage` 仍用 flat `accumulated_usage`（spec：进行中 flat，结束时完整 JSON）

- [ ] **Step 3: 新增便捷方法**

```python
    async def record_llm_call_to_db(
        self,
        raw_usage: Any,
        *,
        parent_node_id: uuid.UUID,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> uuid.UUID | None:
        """Persist llm.round and emit SSE."""

        seq = self.next_llm_round_seq(parent_node_id)
        node_id = await self.usage_tracker.record_llm_call(
            self.db,
            run_id=self.run_id,
            parent_node_id=parent_node_id,
            sequence_idx=seq,
            raw_usage=raw_usage,
            phase=phase,
            step_id=step_id,
            skill_id=skill_id,
        )
        await self.emit_llm_usage(
            raw_usage,
            step_id=step_id,
            skill_id=skill_id,
            phase=phase,
            node_id=str(node_id) if node_id else None,
        )
        return node_id
```

扩展 `emit_llm_usage` 签名增加 `node_id: str | None = None`。

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/graphs/deps.py
git commit -m "feat(agent): wire RunUsageTracker into GraphDeps and SSE"
```

---

### Task 6: Planner 采集

**Files:**
- Modify: `backend/app/agent/graphs/nodes/planner.py`

- [ ] **Step 1: 保存 `plan.created` 节点 id，structured 调用后 record**

将 `insert_run_node` 改为先创建 `plan.created`（status=running），structured 调用后：

```python
    plan_node_id = uuid.uuid4()
    await agent_repo.insert_run_node(..., node_id=plan_node_id, status="running", ...)

    try:
        plan = await structured.ainvoke(planner_messages)
    except Exception:
        ...

    await deps.record_llm_call_to_db(
        plan,  # 若 structured 返回 Plan 无 usage，改用 resp 变量：见下
        parent_node_id=plan_node_id,
        phase="planner",
    )
```

**注意:** `with_structured_output` 的返回值可能是 `Plan` 而非 AIMessage。需在调用后从 LangChain 回调或二次读取 response。实现方式（择一，推荐 A）：

- **A:** `structured = deps.model.with_structured_output(Plan, include_raw=True)`，从 `raw`/`parsed` 取 usage
- **B:** planner 改用 `ainvoke` + 手动 parse（改动大，不采用）

使用 A 时：

```python
    structured = deps.model.with_structured_output(Plan, include_raw=True)
    result = await structured.ainvoke(planner_messages)
    plan = result["parsed"]
    raw_msg = result.get("raw")
    await deps.record_llm_call_to_db(raw_msg, parent_node_id=plan_node_id, phase="planner")
```

- [ ] **Step 2: rollup `plan.created` 节点 `usage_json`**

```python
    await deps.usage_tracker.rollup_children(
        deps.db,
        node_id=plan_node_id,
        child_usage=deps.usage_tracker.document.get("by_phase", {}).get("planner", {}),
    )
```

（若 rollup  helper 需要完整 OpenAIUsage，从 by_phase slice 提取三键。）

- [ ] **Step 3: 更新节点 status=success**

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/graphs/nodes/planner.py
git commit -m "feat(agent): record planner token usage on plan.created node"
```

---

### Task 7: Subagent — `llm.round` 与 step rollup

**Files:**
- Modify: `backend/app/agent/graphs/nodes/subagent_runner.py`
- Modify: `backend/app/agent/graphs/nodes/executor.py`

- [ ] **Step 1: `run_subagent_with_stream` 增加 `parent_node_id: uuid.UUID` 参数**

将 `on_chat_model_end` 处理改为：

```python
            await deps.record_llm_call_to_db(
                data.get("output"),
                parent_node_id=parent_node_id,
                phase="subagent",
                step_id=step.id,
                skill_id=step.skill_id,
            )
```

删除原独立 `emit_llm_usage` 调用（已在 `record_llm_call_to_db` 内）。

- [ ] **Step 2: `executor.py` 传入 `node_id`（subagent.run）**

在 `run_subagent_with_stream(..., parent_node_id=node_id)` 后，根据 tracker 的 `by_step[step.id]` rollup：

```python
    step_usage = (deps.usage_tracker.document.get("by_step") or {}).get(step.id) or {}
    if step_usage:
        await deps.usage_tracker.rollup_children(
            deps.db, node_id=node_id, child_usage=step_usage
        )
```

- [ ] **Step 3: `subagent.finished` SSE 增加 `step_usage`**

```python
    payload={
        ...
        "step_usage": step_usage or None,
    }
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/graphs/nodes/subagent_runner.py backend/app/agent/graphs/nodes/executor.py
git commit -m "feat(agent): persist subagent llm.round nodes and step usage rollup"
```

---

### Task 8: Synthesizer 采集

**Files:**
- Modify: `backend/app/agent/graphs/nodes/synthesizer.py`

- [ ] **Step 1: 节点入口 insert `synthesizer.run`（running）**

```python
    synth_node_id = uuid.uuid4()
    await agent_repo.insert_run_node(
        deps.db,
        node_id=synth_node_id,
        run_id=deps.run_id,
        parent_node_id=None,
        sequence_idx=800,
        node_type="synthesizer.run",
        node_name="synthesizer",
        status="running",
    )
```

- [ ] **Step 2: `_stream_model_text` / `_invoke_model_text` 改为 `record_llm_call_to_db`**

phase=`"synthesizer"`，parent=`synth_node_id`；删除重复 `emit_llm_usage`。

- [ ] **Step 3: 单步直出无 LLM 时跳过 synthesizer 节点或标记 skipped**

`resolve_final_answer_from_subagent_results` 返回非 None 时，将 synthesizer 节点标为 `skipped` 并不 record。

- [ ] **Step 4: rollup + status=success**

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graphs/nodes/synthesizer.py
git commit -m "feat(agent): record synthesizer token usage"
```

---

### Task 9: Run finalize、Session merge、助手消息 meta

**Files:**
- Modify: `backend/app/agent/service/agent_graph_run_service.py`

- [ ] **Step 1: 成功路径 — 使用分层 snapshot**

替换：

```python
                usage_snapshot = deps.usage_tracker.build_run_snapshot()
                ...
                if final_answer:
                    await agent_repo.append_agent_message(
                        ...
                        meta_json={"usage": usage_snapshot} if usage_snapshot else None,
                    )
                await agent_repo.finalize_agent_run(
                    ...
                    usage_json=usage_snapshot or None,
                )
                ...
                if usage_snapshot:
                    finished_payload["usage"] = usage_snapshot
                await agent_repo.merge_session_usage_json(
                    session,
                    session_id=session_id,
                    delta=deps.usage_tracker.build_session_delta(),
                )
```

- [ ] **Step 2: 失败路径 — 仍写部分 usage**

在 `except AppError` / 通用 `except` 的 `finalize_agent_run` 传入 `deps.usage_tracker.build_run_snapshot()`；**成功时才** `merge_session_usage_json`（failed Run 也计入 session：spec 要求 — 失败 finalize 时也 merge session）。

修正：**failed Run 若已有 usage 也 merge session**（与 spec §1.4 一致）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/service/agent_graph_run_service.py
git commit -m "feat(agent): persist layered run usage and merge session totals"
```

---

### Task 10: 后台 `memory.persist` patch

**Files:**
- Modify: `backend/app/agent/service/memory_persist_service.py`
- Create: `backend/tests/test_agent_memory_persist_usage.py`

- [ ] **Step 1: 写失败测试（mock model 与 repo）**

验证 `invoke_memory_extract` 后调用 `merge_run_usage_json`、`merge_session_usage_json`、`patch_assistant_message_usage_by_run`，且 `by_phase.memory.persist` 存在。

- [ ] **Step 2: 在 extract 成功后 record**

独立 session 内构造临时 `RunUsageTracker` 或直接用 `merge_run_usage_json` + `build_phase_delta("memory.persist", usage)`：

```python
        extract = await invoke_memory_extract(model, ...)
        usage = normalize_openai_usage(getattr(extract, "usage_metadata", None))  # 或从 AIMessage
        if not usage:
            usage = extract_usage_from_langchain_output(extract_raw_message)
        if usage:
            delta = build_phase_delta("memory.persist", usage)
            await agent_repo.merge_run_usage_json(session, run_id=run_id, delta=delta)
            run_row = await session.get(AgentRun, run_id)
            if run_row and isinstance(run_row.usage_json, dict):
                await agent_repo.merge_session_usage_json(
                    session, session_id=session_id, delta=run_row.usage_json
                )
                await agent_repo.patch_assistant_message_usage_by_run(
                    session, run_id=run_id, usage_json=run_row.usage_json
                )
        await session.commit()
```

**注意:** 确认 `invoke_memory_extract` 返回值；若仅返回 `MemoryExtract` Pydantic，需让该函数返回 `(extract, raw_message)` 或在内部暴露 usage。

- [ ] **Step 3: 运行测试 + Commit**

Run: `cd backend && pytest tests/test_agent_memory_persist_usage.py -v`

```bash
git add backend/app/agent/service/memory_persist_service.py backend/tests/test_agent_memory_persist_usage.py
git commit -m "feat(agent): patch run/session/message usage after memory.persist"
```

---

### Task 11: HTTP API — Session `usage`

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`
- Create: `backend/tests/test_agent_session_usage_api.py`

- [ ] **Step 1: Pydantic 增加字段**

```python
class AgentSessionOut(BaseModel):
    ...
    usage: dict | None = Field(default=None, description="累计 token 用量(JSON，同 usage_json)")


class AgentSessionListItemOut(BaseModel):
    ...
    usage: dict | None = None
```

- [ ] **Step 2: Router 映射**

```python
        session=AgentSessionOut(
            ...
            usage=row.usage_json if isinstance(row.usage_json, dict) else None,
        ),
```

列表项同样传入 `usage=row.usage_json ...`。

- [ ] **Step 3: API 测试（使用现有 test client 模式）**

至少断言 detail/list JSON 含 `usage` 键（可为 null）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/router.py backend/tests/test_agent_session_usage_api.py
git commit -m "feat(agent): expose session usage on v2 API"
```

---

### Task 12: 前端 — 刷新恢复与类型

**Files:**
- Modify: `frontend/src/api/agent.ts`
- Modify: `frontend/src/features/agent/agentSkillUi.ts`
- Modify: `frontend/src/features/agent/AgentsPage.tsx`

**说明:** 复制按钮旁 token 展示已在当前分支部分实现；本 Task 补齐持久化恢复。

- [ ] **Step 1: API 类型**

```typescript
export type AgentUsage = {
  prompt_tokens?: number
  completion_tokens?: number
  total_tokens?: number
  by_phase?: Record<string, AgentUsage>
  details?: Record<string, number>
}

export type AgentSessionOut = {
  ...
  usage?: AgentUsage | null
}
```

- [ ] **Step 2: `agentMessagesToChat` 从 `meta_json.usage` 解析**

API 需扩展 message 输出含 `meta_json`（若当前无）：

后端 `AgentMessageOut` 增加 `meta_json: dict | None = None`，router 传入 `m.meta_json`。

前端：

```typescript
function totalTokensFromUsage(raw: unknown): number | undefined {
  ...
}

export function agentMessagesToChat(
  rows: { id: string; role: string; content: string | null; meta_json?: unknown }[],
): AgentChatMsg[] {
  ...
  const usage = (m.meta_json as { usage?: unknown } | null)?.usage
  const totalTokens = totalTokensFromUsage(usage)
  out.push({ id: m.id, role: m.role, content: m.content ?? '', totalTokens })
}
```

- [ ] **Step 3: 加载会话 detail 时使用 server 解析的 totalTokens**

`mergeAgentChatWithLocal` 已保留 `totalTokens`；确保 server 值优先：

```typescript
totalTokens: totalTokensFromUsage((sm as any).meta...) ?? src?.totalTokens,
```

（实现时用 typed message row。）

- [ ] **Step 4: （可选）侧栏展示 session.usage.total_tokens**

在 session 列表行 subtitle 追加 muted token 数。

- [ ] **Step 5: 手动验证**

1. 发起一轮对话 → Run 结束 → 复制按钮旁出现 `N tokens`
2. 刷新页面 → 同一助手消息仍显示 token
3. 等待 memory.persist 完成后再刷新 → token 数包含 memory 阶段（若后端 patch 消息 meta）

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/agent.ts frontend/src/features/agent/agentSkillUi.ts frontend/src/features/agent/AgentsPage.tsx backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/router.py
git commit -m "feat(ui): restore per-message token usage from API meta"
```

---

### Task 13: 文档回填

**Files:**
- Modify: `docs/superpowers/specs/2026-05-26-agent-token-usage-design.md`
- Modify: `docs/agent-module-design.md`

- [ ] **Step 1: 更新 spec 状态与 §10 实现对照表**（每项标记已实现 + 代码路径）

- [ ] **Step 2: 更新 `agent-module-design.md`**

- §7 表：`agent_run_node.usage_json`、`agent_session.usage_json`
- §9.2：`run.finished.usage` 分层结构；`llm.usage.node_id`；助手消息 `meta_json.usage`

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-26-agent-token-usage-design.md docs/agent-module-design.md
git commit -m "docs(agent): backfill token usage design and module doc"
```

---

### Task 14: 全量回归

- [ ] **Step 1: 运行 Agent 相关测试**

Run: `cd backend && pytest tests/test_agent_openai_usage.py tests/test_agent_usage_tracker.py tests/test_agent_memory_persist_usage.py tests/test_agent_session_usage_api.py tests/test_agent_graph_compile.py tests/test_agent_synthesizer.py -v`

Expected: 全部 PASS

- [ ] **Step 2: 前端 typecheck（若项目有）**

Run: `cd frontend && npm run build`（或 `npm run lint`）

Expected: 无 TS 错误

---

## Plan self-review（已完成）

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §2 usage_json 结构 | Task 2 |
| §3 数据模型 | Task 1 |
| §4 采集与数据流 | Task 3–10 |
| §5 SSE | Task 5, 7, 9 |
| §6 HTTP API | Task 11 |
| §7 前端 | Task 12 |
| §8 测试 | Task 2, 3, 10, 11, 14 |
| §9 文档 | Task 13 |

**补充（UX）:** 助手消息 `meta_json.usage` + memory.persist 后 patch — Task 9–10, 12（spec 未写明细，为实现「刷新后仍显示 tokens」所需）。

**Placeholder 扫描:** 无 TBD/TODO 步骤。

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-26-agent-token-usage.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间人工/自动 review，迭代快  
2. **Inline Execution** — 本会话按 Task 顺序直接实现，批次间设检查点

你希望用哪种方式开始实现？
