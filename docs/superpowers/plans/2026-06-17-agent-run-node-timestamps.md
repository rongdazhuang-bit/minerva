# Agent Run Node 时间戳与终态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为新 Agent Run 补齐 `agent_run_node.started_at` / `finished_at`，统一两阶段生命周期（begin → finalize），修复父节点 stuck `running`，并实现子节点 `failed` 向上传播。

**Architecture:** 在 `repository.py` 集中实现 `begin_run_node` / `finalize_run_node` / `insert_terminal_run_node` 及失败传播；`RunUsageTracker` 与 `GraphDeps` 将 `llm.round` 拆为 begin/finalize；各 graph 节点与 memory persist 策略改为调用统一 API，不再直接 `insert_run_node` + 手改 `status`。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async, PostgreSQL, LangChain/LangGraph, pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-06-17-agent-run-node-timestamps-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/app/agent/infrastructure/repository.py` | `begin_run_node`、`finalize_run_node`、`insert_terminal_run_node`、`_propagate_failure_to_parent` |
| `backend/tests/test_run_node_lifecycle.py` | **新建** lifecycle 与失败传播单测 |
| `backend/app/agent/infrastructure/usage_tracker.py` | `begin_llm_round` / `finalize_llm_round` 替代一次性 `record_llm_call` |
| `backend/tests/test_agent_usage_tracker.py` | **新建/恢复** tracker begin/finalize 单测 |
| `backend/app/agent/graphs/deps.py` | `begin_llm_call_to_db` / `finalize_llm_call_to_db` |
| `backend/app/agent/graphs/nodes/planner.py` | `plan.created` 两阶段 + planner LLM 两阶段 |
| `backend/app/agent/graphs/nodes/executor.py` | `subagent.run` finalize + `insert_terminal_run_node` for finish |
| `backend/app/agent/graphs/nodes/subagent_runner.py` | subagent LLM begin/finalize（stream + fallback） |
| `backend/app/agent/graphs/nodes/synthesizer.py` | synthesizer.run finalize + LLM 两阶段 |
| `backend/app/agent/memory/sql/persist.py` | memory.persist finalize + extract LLM 两阶段 |
| `backend/app/agent/memory/mem0/persist.py` | memory.persist finalize + terminal done/failed |
| `docs/superpowers/specs/2026-06-17-agent-run-node-timestamps-design.md` | 状态 + 实现对照 |
| `docs/agent-module-design.md` | § 节点树 / 实现对照回填 |

---

### Task 1: Repository 生命周期 API

**Files:**
- Modify: `backend/app/agent/infrastructure/repository.py`
- Create: `backend/tests/test_run_node_lifecycle.py`

- [ ] **Step 1: 创建测试目录与失败测试**

```bash
mkdir -p backend/tests
```

`backend/tests/test_run_node_lifecycle.py`:

```python
"""Tests for agent_run_node begin/finalize lifecycle and failure propagation."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.domain.db.models import AgentRunNode
from app.agent.infrastructure import repository as agent_repo


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar_one_or_none(self) -> Any:
        return self._value


class FakeAsyncSession:
    """Minimal in-memory AsyncSession for repository unit tests."""

    def __init__(self) -> None:
        self.rows: dict[uuid.UUID, AgentRunNode] = {}

    def add(self, row: AgentRunNode) -> None:
        self.rows[row.id] = row

    async def get(self, model: type, key: uuid.UUID) -> AgentRunNode | None:
        return self.rows.get(key)

    async def execute(self, stmt: Any) -> _FakeResult:
        # Only used by finalize_run_node child-failed check; inspect WHERE manually.
        compiled = str(stmt)
        if "agent_run_node.status" in compiled and "failed" in compiled:
            for row in self.rows.values():
                if row.status == "failed":
                    return _FakeResult(row.id)
            return _FakeResult(None)
        return _FakeResult(None)

    async def flush(self) -> None:
        return None


@pytest.mark.asyncio
async def test_begin_run_node_sets_started_at_and_running() -> None:
    """begin_run_node writes running status and started_at only."""

    session = FakeAsyncSession()
    node_id = uuid.uuid4()
    run_id = uuid.uuid4()
    row = await agent_repo.begin_run_node(
        session,  # type: ignore[arg-type]
        node_id=node_id,
        run_id=run_id,
        parent_node_id=None,
        sequence_idx=1,
        node_type="plan.created",
        node_name="planner",
    )
    assert row.status == "running"
    assert row.started_at is not None
    assert row.finished_at is None


@pytest.mark.asyncio
async def test_finalize_run_node_sets_finished_at() -> None:
    """finalize_run_node writes terminal status and finished_at."""

    session = FakeAsyncSession()
    node_id = uuid.uuid4()
    await agent_repo.begin_run_node(
        session,  # type: ignore[arg-type]
        node_id=node_id,
        run_id=uuid.uuid4(),
        parent_node_id=None,
        sequence_idx=1,
        node_type="plan.created",
        node_name="planner",
    )
    await agent_repo.finalize_run_node(
        session,  # type: ignore[arg-type]
        node_id=node_id,
        status="success",
        outputs_json={"step_count": 1},
    )
    row = session.rows[node_id]
    assert row.status == "success"
    assert row.finished_at is not None
    assert row.outputs_json == {"step_count": 1}


@pytest.mark.asyncio
async def test_child_failed_propagates_to_running_parent() -> None:
    """When a child finalizes failed, running parent becomes failed."""

    session = FakeAsyncSession()
    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()
    run_id = uuid.uuid4()
    await agent_repo.begin_run_node(
        session,  # type: ignore[arg-type]
        node_id=parent_id,
        run_id=run_id,
        parent_node_id=None,
        sequence_idx=1,
        node_type="subagent.run",
        node_name="file",
    )
    await agent_repo.begin_run_node(
        session,  # type: ignore[arg-type]
        node_id=child_id,
        run_id=run_id,
        parent_node_id=parent_id,
        sequence_idx=0,
        node_type="llm.round",
        node_name="subagent",
    )
    await agent_repo.finalize_run_node(
        session,  # type: ignore[arg-type]
        node_id=child_id,
        status="failed",
        error_message="boom",
    )
    parent = session.rows[parent_id]
    assert parent.status == "failed"
    assert parent.finished_at is not None


@pytest.mark.asyncio
async def test_insert_terminal_run_node_equal_timestamps() -> None:
    """Terminal nodes get started_at == finished_at at insert."""

    session = FakeAsyncSession()
    node_id = uuid.uuid4()
    row = await agent_repo.insert_terminal_run_node(
        session,  # type: ignore[arg-type]
        node_id=node_id,
        run_id=uuid.uuid4(),
        parent_node_id=uuid.uuid4(),
        sequence_idx=0,
        node_type="subagent.finish",
        node_name="file",
        status="success",
        outputs_json={"chars": 10},
    )
    assert row.status == "success"
    assert row.started_at == row.finished_at
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_run_node_lifecycle.py -v`

Expected: FAIL — `ImportError` or `AttributeError: begin_run_node`

- [ ] **Step 3: 在 `repository.py` 实现 lifecycle 函数**

在 `insert_run_node` **之前**追加（保留 `insert_run_node` 供旧调用过渡，Task 4+ 逐步替换）：

```python
def _utc_now() -> datetime:
    """Return current UTC timestamp for run node lifecycle fields."""

    return datetime.now(timezone.utc)


async def _propagate_failure_to_parent(
    session: AsyncSession,
    *,
    parent_node_id: uuid.UUID,
) -> None:
    """Mark parent (and ancestors) failed when a child node fails."""

    parent = await session.get(AgentRunNode, parent_node_id)
    if parent is None:
        return
    now = _utc_now()
    parent.status = "failed"
    if parent.finished_at is None:
        parent.finished_at = now
    if parent.parent_node_id is not None:
        await _propagate_failure_to_parent(session, parent_node_id=parent.parent_node_id)
    await session.flush()


async def _run_node_has_failed_child(session: AsyncSession, *, node_id: uuid.UUID) -> bool:
    """Return True when any direct child of ``node_id`` has status failed."""

    stmt = (
        select(AgentRunNode.id)
        .where(
            AgentRunNode.parent_node_id == node_id,
            AgentRunNode.status == "failed",
        )
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none() is not None


async def begin_run_node(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    run_id: uuid.UUID,
    parent_node_id: uuid.UUID | None,
    sequence_idx: int,
    node_type: str,
    node_name: str,
    inputs_json: dict[str, Any] | list[Any] | None = None,
    meta_json: dict[str, Any] | list[Any] | None = None,
) -> AgentRunNode:
    """Insert a run node in ``running`` state with ``started_at`` set."""

    now = _utc_now()
    row = AgentRunNode(
        id=node_id,
        run_id=run_id,
        parent_node_id=parent_node_id,
        sequence_idx=sequence_idx,
        node_type=node_type,
        node_name=node_name,
        status="running",
        inputs_json=inputs_json,
        meta_json=meta_json,
        started_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def finalize_run_node(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    status: str,
    outputs_json: dict[str, Any] | list[Any] | None = None,
    usage_json: dict[str, Any] | list[Any] | None = None,
    reasoning_text: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """Finalize a run node; propagate ``failed`` to parents; coerce success when child failed."""

    row = await session.get(AgentRunNode, node_id)
    if row is None:
        return
    final_status = status
    if final_status == "success" and await _run_node_has_failed_child(session, node_id=node_id):
        final_status = "failed"
    now = _utc_now()
    row.status = final_status
    row.finished_at = now
    if outputs_json is not None:
        row.outputs_json = outputs_json
    if usage_json is not None:
        row.usage_json = usage_json
    if reasoning_text is not None:
        row.reasoning_text = reasoning_text
    row.error_code = error_code
    row.error_message = error_message
    await session.flush()
    if final_status == "failed" and row.parent_node_id is not None:
        await _propagate_failure_to_parent(session, parent_node_id=row.parent_node_id)


async def insert_terminal_run_node(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    run_id: uuid.UUID,
    parent_node_id: uuid.UUID | None,
    sequence_idx: int,
    node_type: str,
    node_name: str,
    status: str,
    inputs_json: dict[str, Any] | list[Any] | None = None,
    outputs_json: dict[str, Any] | list[Any] | None = None,
    meta_json: dict[str, Any] | list[Any] | None = None,
    usage_json: dict[str, Any] | list[Any] | None = None,
    reasoning_text: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> AgentRunNode:
    """Insert a node that completes immediately (``started_at == finished_at``)."""

    now = _utc_now()
    row = AgentRunNode(
        id=node_id,
        run_id=run_id,
        parent_node_id=parent_node_id,
        sequence_idx=sequence_idx,
        node_type=node_type,
        node_name=node_name,
        status=status,
        inputs_json=inputs_json,
        outputs_json=outputs_json,
        meta_json=meta_json,
        usage_json=usage_json,
        reasoning_text=reasoning_text,
        error_code=error_code,
        error_message=error_message,
        started_at=now,
        finished_at=now,
    )
    session.add(row)
    await session.flush()
    if status == "failed" and parent_node_id is not None:
        await _propagate_failure_to_parent(session, parent_node_id=parent_node_id)
    return row
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_run_node_lifecycle.py -v`

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/repository.py backend/tests/test_run_node_lifecycle.py
git commit -m "feat(agent): add run node begin/finalize lifecycle helpers"
```

---

### Task 2: RunUsageTracker LLM 两阶段

**Files:**
- Modify: `backend/app/agent/infrastructure/usage_tracker.py`
- Create: `backend/tests/test_agent_usage_tracker.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_agent_usage_tracker.py`:

```python
"""Tests for RunUsageTracker LLM round begin/finalize."""

from __future__ import annotations

import uuid

import pytest

from app.agent.infrastructure.usage_tracker import RunUsageTracker


@pytest.mark.asyncio
async def test_begin_llm_round_inserts_running_node(monkeypatch: pytest.MonkeyPatch) -> None:
    """begin_llm_round calls begin_run_node with running status."""

    calls: list[dict] = []

    async def fake_begin(session, **kwargs):
        calls.append(kwargs)
        return type("Row", (), {"id": kwargs["node_id"]})()

    monkeypatch.setattr(
        "app.agent.infrastructure.repository.begin_run_node",
        fake_begin,
    )

    tracker = RunUsageTracker()
    node_id = uuid.uuid4()
    out = await tracker.begin_llm_round(
        session=object(),
        node_id=node_id,
        run_id=uuid.uuid4(),
        parent_node_id=uuid.uuid4(),
        sequence_idx=0,
        phase="planner",
    )
    assert out == node_id
    assert calls[0]["node_type"] == "llm.round"
    assert calls[0]["node_name"] == "planner"


@pytest.mark.asyncio
async def test_finalize_llm_round_merges_usage_and_finalizes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """finalize_llm_round records usage in memory and finalizes node."""

    finalized: list[dict] = []

    async def fake_finalize(session, **kwargs):
        finalized.append(kwargs)

    monkeypatch.setattr(
        "app.agent.infrastructure.repository.finalize_run_node",
        fake_finalize,
    )

    tracker = RunUsageTracker()
    node_id = uuid.uuid4()
    await tracker.finalize_llm_round(
        session=object(),
        node_id=node_id,
        raw_usage={"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        phase="planner",
        status="success",
    )
    assert tracker.flat_total["total_tokens"] == 5
    assert finalized[0]["node_id"] == node_id
    assert finalized[0]["status"] == "success"
    assert finalized[0]["usage_json"]["total_tokens"] == 5
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_agent_usage_tracker.py -v`

Expected: FAIL — `AttributeError: begin_llm_round`

- [ ] **Step 3: 改造 `usage_tracker.py`**

保留 `record_call`；将 `record_llm_call` 拆为：

```python
    async def begin_llm_round(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        run_id: uuid.UUID,
        parent_node_id: uuid.UUID | None,
        sequence_idx: int,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> uuid.UUID:
        """Insert ``llm.round`` in running state before the upstream LLM call."""

        meta: dict[str, Any] = {"phase": phase}
        if step_id is not None:
            meta["step_id"] = step_id
        if skill_id is not None:
            meta["skill_id"] = skill_id
        await agent_repo.begin_run_node(
            session,
            node_id=node_id,
            run_id=run_id,
            parent_node_id=parent_node_id,
            sequence_idx=sequence_idx,
            node_type="llm.round",
            node_name=phase,
            meta_json=meta,
        )
        return node_id

    async def finalize_llm_round(
        self,
        session: AsyncSession,
        *,
        node_id: uuid.UUID,
        raw_usage: Any,
        phase: str,
        status: str = "success",
        step_id: str | None = None,
        skill_id: str | None = None,
        reasoning_text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Finalize ``llm.round`` after LLM returns or raises."""

        usage_doc = self.record_call(
            raw_usage,
            phase=phase,
            step_id=step_id,
            skill_id=skill_id,
        )
        usage_payload = (
            usage_document_for_node(usage_doc) if usage_doc else None
        )
        await agent_repo.finalize_run_node(
            session,
            node_id=node_id,
            status=status,
            usage_json=usage_payload,
            reasoning_text=reasoning_text,
            error_message=error_message,
        )
```

删除或保留 `record_llm_call` 为 thin wrapper（内部 begin+finalize 同时调用）**不要保留** — Task 3 会改所有 call site。若仍有引用，改为 `raise DeprecationWarning` 或直接删除并在 Task 3 一并修复。

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_agent_usage_tracker.py -v`

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/usage_tracker.py backend/tests/test_agent_usage_tracker.py
git commit -m "feat(agent): split llm.round into begin and finalize in usage tracker"
```

---

### Task 3: GraphDeps LLM 两阶段

**Files:**
- Modify: `backend/app/agent/graphs/deps.py`

- [ ] **Step 1: 替换 `record_llm_call_to_db`**

在 `GraphDeps` 中删除 `record_llm_call_to_db`，新增：

```python
    async def begin_llm_call_to_db(
        self,
        *,
        parent_node_id: uuid.UUID,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
    ) -> uuid.UUID:
        """Insert ``llm.round`` (running) before an upstream LLM call."""

        seq = self.next_llm_round_seq(parent_node_id)
        node_id = uuid.uuid4()
        await self.usage_tracker.begin_llm_round(
            self.db,
            node_id=node_id,
            run_id=self.run_id,
            parent_node_id=parent_node_id,
            sequence_idx=seq,
            phase=phase,
            step_id=step_id,
            skill_id=skill_id,
        )
        return node_id

    async def finalize_llm_call_to_db(
        self,
        node_id: uuid.UUID | None,
        raw_usage: Any,
        *,
        phase: str,
        step_id: str | None = None,
        skill_id: str | None = None,
        status: str = "success",
        reasoning_text: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Finalize ``llm.round`` and emit ``llm.usage`` SSE when applicable."""

        if node_id is None:
            return
        await self.usage_tracker.finalize_llm_round(
            self.db,
            node_id=node_id,
            raw_usage=raw_usage,
            phase=phase,
            status=status,
            step_id=step_id,
            skill_id=skill_id,
            reasoning_text=reasoning_text,
            error_message=error_message,
        )
        if status == "success":
            await self.emit_llm_usage(
                raw_usage,
                step_id=step_id,
                skill_id=skill_id,
                phase=phase,
                node_id=str(node_id),
            )
```

- [ ] **Step 2: 全局搜索旧 API 引用（暂不改 call site，确认仅 deps 定义处）**

Run: `cd backend && rg "record_llm_call_to_db" app/agent`

Expected: 仅 `deps.py` 定义 + planner/synthesizer/subagent_runner 调用（Task 4–6 修改）

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/graphs/deps.py
git commit -m "feat(agent): add begin/finalize llm call helpers on GraphDeps"
```

---

### Task 4: Planner 节点

**Files:**
- Modify: `backend/app/agent/graphs/nodes/planner.py`

- [ ] **Step 1: 将 `insert_run_node` 改为 `begin_run_node`**

替换 planner 入口：

```python
    await agent_repo.begin_run_node(
        deps.db,
        node_id=plan_node_id,
        run_id=deps.run_id,
        parent_node_id=None,
        sequence_idx=1,
        node_type="plan.created",
        node_name="planner",
    )
```

- [ ] **Step 2: LLM 两阶段包裹 structured 调用**

```python
    llm_node_id: uuid.UUID | None = None
    raw_msg = None
    try:
        llm_node_id = await deps.begin_llm_call_to_db(
            parent_node_id=plan_node_id,
            phase="planner",
        )
        result = await structured.ainvoke(planner_messages)
        # ... existing parse logic ...
    except Exception:
        if llm_node_id is not None:
            await deps.finalize_llm_call_to_db(
                llm_node_id,
                {},
                phase="planner",
                status="failed",
                error_message="planner structured output failed",
            )
        fallback = plan_fallback_skill_id(request_text)
        plan = Plan(steps=[PlanStep(id="s1", skill_id=fallback, goal=request_text)])
```

成功路径在 `raw_msg is not None` 块：

```python
        await deps.finalize_llm_call_to_db(
            llm_node_id,
            raw_msg,
            phase="planner",
            reasoning_text=reasoning_text or None,
        )
```

删除对 `record_llm_call_to_db` 的调用。

- [ ] **Step 3: finalize `plan.created`**

替换末尾（`finalize_run_node` 会在存在 failed 子节点时自动将 success 降为 failed）：

```python
    await agent_repo.finalize_run_node(
        deps.db,
        node_id=plan_node_id,
        status="success",
        outputs_json={"step_count": len(plan.steps)},
    )
```

删除 `plan_node = await deps.db.get(...); plan_node.status = ...` 手改逻辑。

**Planner 异常语义：** structured 解析失败但 upstream 已返回时，`llm.round` 应 finalize 为 `success`（携带 usage）；仅 `ainvoke` 抛错时 finalize 为 `failed`。这样 fallback plan 路径下 `plan.created` 仍可 success。

- [ ] **Step 4: 语法检查**

Run: `cd backend && python -c "from app.agent.graphs.nodes.planner import planner_node; print('ok')"`

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graphs/nodes/planner.py
git commit -m "feat(agent): planner run node lifecycle and llm.round two-phase"
```

---

### Task 5: Subagent runner + Executor

**Files:**
- Modify: `backend/app/agent/graphs/nodes/subagent_runner.py`
- Modify: `backend/app/agent/graphs/nodes/executor.py`

- [ ] **Step 1: `subagent_runner.py` — stream 路径 LLM 两阶段**

在 `async for event in subagent.astream_events` 循环内：

- `event == "on_chat_model_start"` → 从 event data 取 run 信息，调用 `begin_llm_call_to_db`；用 `dict` 缓存 `parent_run_id → llm_node_id`（LangChain run_id 作 key）
- `event == "on_chat_model_end"` → 取缓存 node_id，调用 `finalize_llm_call_to_db`；删除原 `record_llm_call_to_db`

示例片段：

```python
    pending_llm_nodes: dict[str, uuid.UUID] = {}

    async for event in subagent.astream_events(inputs, config=config_sub, version="v2"):
        if event.get("event") == "on_chat_model_start":
            run_id_key = str((event.get("run_id") or ""))
            pending_llm_nodes[run_id_key] = await deps.begin_llm_call_to_db(
                parent_node_id=parent_node_id,
                phase="subagent",
                step_id=step.id,
                skill_id=step.skill_id,
            )
        if event.get("event") == "on_chat_model_end":
            data = event.get("data") or {}
            llm_output = data.get("output")
            run_id_key = str((event.get("run_id") or ""))
            llm_node_id = pending_llm_nodes.pop(run_id_key, None)
            await deps.finalize_llm_call_to_db(
                llm_node_id,
                llm_output,
                phase="subagent",
                step_id=step.id,
                skill_id=step.skill_id,
                reasoning_text=extract_reasoning_from_langchain_message(llm_output) or None,
            )
            subagent_reasoning_tokens += reasoning_tokens_from_raw(llm_output)
```

- [ ] **Step 2: `subagent_runner.py` — fallback `ainvoke` 路径**

```python
        llm_node_id = await deps.begin_llm_call_to_db(
            parent_node_id=parent_node_id,
            phase="subagent",
            step_id=step.id,
            skill_id=step.skill_id,
        )
        result = await subagent.ainvoke(inputs, config=config_sub)
        # ... find assistant msg ...
        await deps.finalize_llm_call_to_db(
            llm_node_id,
            msg,
            phase="subagent",
            step_id=step.id,
            skill_id=step.skill_id,
            reasoning_text=round_text or None,
        )
```

- [ ] **Step 3: `executor.py` — subagent.run begin/finalize**

将 `insert_run_node(..., status="running")` 改为 `begin_run_node(...)`。

在写 `subagent.finish` 之前 finalize 父节点：

```python
    finish_status = "success" if step.status == "success" else "failed"
    await agent_repo.finalize_run_node(
        deps.db,
        node_id=node_id,
        status=finish_status,
    )
```

将第二个 `insert_run_node`（subagent.finish）改为：

```python
    await agent_repo.insert_terminal_run_node(
        deps.db,
        node_id=uuid.uuid4(),
        run_id=deps.run_id,
        parent_node_id=node_id,
        sequence_idx=0,
        node_type="subagent.finish",
        node_name=step.skill_id,
        status=finish_status,
        outputs_json={"chars": len(output)},
    )
```

- [ ] **Step 4: 语法检查**

Run: `cd backend && python -c "from app.agent.graphs.nodes.executor import executor_node; from app.agent.graphs.nodes.subagent_runner import run_subagent_with_stream; print('ok')"`

Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graphs/nodes/subagent_runner.py backend/app/agent/graphs/nodes/executor.py
git commit -m "feat(agent): subagent llm.round two-phase and subagent.run finalize"
```

---

### Task 6: Synthesizer 节点

**Files:**
- Modify: `backend/app/agent/graphs/nodes/synthesizer.py`

- [ ] **Step 1: `synthesizer.run` 改用 `begin_run_node`**

替换 `insert_run_node(..., status="running")` 为 `begin_run_node(...)`。

- [ ] **Step 2: `_stream_model_text` LLM 两阶段**

```python
    llm_node_id = await deps.begin_llm_call_to_db(
        parent_node_id=synth_node_id,
        phase="synthesizer",
    )
    try:
        async for chunk in deps.model.astream(messages):
            # ... existing stream logic ...
    finally:
        if last_usage is not None:
            await deps.finalize_llm_call_to_db(
                llm_node_id,
                last_usage,
                phase="synthesizer",
                reasoning_text=reasoning_text or None,
            )
        elif llm_node_id is not None:
            await deps.finalize_llm_call_to_db(
                llm_node_id,
                {},
                phase="synthesizer",
                status="failed",
                error_message="synthesizer stream produced no usage",
            )
```

若 stream 无 usage 但成功返回文本，可将 finalize status 仍为 `success` 且 `raw_usage={}`（按产品偏好；默认 success）。

- [ ] **Step 3: `_invoke_model_text` LLM 两阶段**

```python
    llm_node_id = await deps.begin_llm_call_to_db(
        parent_node_id=synth_node_id,
        phase="synthesizer",
    )
    resp = await deps.model.ainvoke(messages)
    # ... reasoning ...
    await deps.finalize_llm_call_to_db(
        llm_node_id,
        resp,
        phase="synthesizer",
        reasoning_text=reasoning_text or None,
    )
```

- [ ] **Step 4: `_finalize_synthesizer_node` 改用 `finalize_run_node`**

```python
    await agent_repo.finalize_run_node(
        deps.db,
        node_id=synth_node_id,
        status="success",
    )
```

删除 `synth_node.status = "success"` 手改。

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/graphs/nodes/synthesizer.py
git commit -m "feat(agent): synthesizer run node lifecycle and llm.round two-phase"
```

---

### Task 7: Memory persist（SQL + mem0）

**Files:**
- Modify: `backend/app/agent/memory/sql/persist.py`
- Modify: `backend/app/agent/memory/mem0/persist.py`

- [ ] **Step 1: `sql/persist.py` — begin memory.persist**

将首个 `insert_run_node(..., status="running")` 改为 `begin_run_node(...)`。

- [ ] **Step 2: extract LLM 两阶段**

在 `invoke_memory_extract` 前后（无 GraphDeps，直接调 repository + tracker 或内联 begin/finalize）：

```python
            llm_node_id = uuid.uuid4()
            await agent_repo.begin_run_node(
                session,
                node_id=llm_node_id,
                run_id=run_id,
                parent_node_id=node_id,
                sequence_idx=0,
                node_type="llm.round",
                node_name="memory.persist",
                meta_json={"phase": "memory.persist"},
            )
            try:
                extract, raw_llm = await invoke_memory_extract(
                    model,
                    user_message=user_text,
                    final_answer=final,
                )
                usage_doc = extract_usage_document(raw_llm)
                await agent_repo.finalize_run_node(
                    session,
                    node_id=llm_node_id,
                    status="success",
                    usage_json=usage_document_for_node(usage_doc) if usage_doc else None,
                )
            except Exception as exc:
                await agent_repo.finalize_run_node(
                    session,
                    node_id=llm_node_id,
                    status="failed",
                    error_message=str(exc)[:500],
                )
                raise
```

删除原一次性 `insert_run_node` llm.round 块。

- [ ] **Step 3: done 子节点 + finalize 父节点**

将 success 路径末尾 `insert_run_node(..., memory.persist/done)` 改为 `insert_terminal_run_node(...)`。

在 try 块成功结束前：

```python
            await agent_repo.finalize_run_node(
                session,
                node_id=node_id,
                status="success",
            )
```

在 except 块：

```python
            await agent_repo.finalize_run_node(
                session,
                node_id=node_id,
                status="failed",
                error_message=str(e)[:500],
            )
```

- [ ] **Step 4: `mem0/persist.py` 同样改造**

- `begin_run_node` for parent
- `insert_terminal_run_node` for done/failed children
- `finalize_run_node` on parent success/failure

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/memory/sql/persist.py backend/app/agent/memory/mem0/persist.py
git commit -m "feat(agent): memory.persist run node lifecycle and llm.round two-phase"
```

---

### Task 8: 清理旧 API + 文档回填

**Files:**
- Modify: `backend/app/agent/infrastructure/usage_tracker.py`（若仍保留 `record_llm_call` 则删除）
- Modify: `docs/superpowers/specs/2026-06-17-agent-run-node-timestamps-design.md`
- Modify: `docs/agent-module-design.md`

- [ ] **Step 1: 确认无 `record_llm_call_to_db` / `record_llm_call` 残留**

Run: `cd backend && rg "record_llm_call" app/agent`

Expected: 无匹配（或仅注释）

- [ ] **Step 2: 运行相关测试**

Run: `cd backend && python -m pytest tests/test_run_node_lifecycle.py tests/test_agent_usage_tracker.py -v`

Expected: all passed

- [ ] **Step 3: 更新 spec 状态与实现对照**

在 `2026-06-17-agent-run-node-timestamps-design.md` 文首：

```markdown
**状态**：已实现（2026-06-17）
```

更新 §10 实现对照表各行为「已实现」并填代码路径。

- [ ] **Step 4: 更新 `docs/agent-module-design.md`**

在节点树 / observability 小节追加一句：`agent_run_node.started_at/finished_at` 由 `begin_run_node` / `finalize_run_node` 维护；子 failed 向上传播。

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-06-17-agent-run-node-timestamps-design.md docs/agent-module-design.md
git commit -m "docs(agent): mark run node timestamp spec implemented"
```

---

## Spec coverage checklist

| Spec § | Task |
|--------|------|
| §2 时间戳语义 | Task 1 `begin_run_node` / `insert_terminal_run_node` |
| §3 Repository API | Task 1 |
| §4 失败传播 | Task 1 tests + all finalize paths |
| §5 llm.round 两阶段 | Task 2, 3, 4, 5, 6, 7 |
| §6 父节点改造 | Task 4, 5, 6, 7 |
| §7 错误处理 | Task 4–7 try/except finalize failed |
| §8 测试 | Task 1, 2 |
| §9 非目标（无回填/API/cancel） | 无对应 task（符合 spec） |
| §10 文档 | Task 8 |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-17-agent-run-node-timestamps.md`.

**Two execution options:**

1. **Subagent-Driven (recommended)** — 每个 Task 派发独立 subagent，任务间做 review，迭代快  
2. **Inline Execution** — 本会话按 Task 顺序直接实现，批次间设 checkpoint

**Which approach?**
