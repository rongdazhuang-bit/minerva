# Agent LangGraph 大改 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用 LangGraph（Plan-and-Execute + 子 Agent）替换 `app/agent` 自研编排，新增 SQL 长期记忆、SSE v2、API v2（`model_id` 服务端托管），并同步更新 `frontend`。

**Architecture:** 外层主图 `memory.retrieve → planner → executor → synthesizer → memory.persist`；子 Agent 为 `create_react_agent`（`general` / `file` / `datetime`）；`AgentGraphEventMapper` 将 `astream_events` 映射为 SSE v2；持久化沿用并扩展 `agent_*` 表 + LangGraph `AsyncPostgresSaver`。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 async, PostgreSQL, LangGraph, LangChain, langchain-openai, langgraph-checkpoint-postgres, pytest, React/frontend

**Spec:** `docs/superpowers/specs/2026-05-16-agent-langgraph-redesign-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| File | Responsibility |
|------|----------------|
| `backend/pyproject.toml` | LangChain/LangGraph 依赖 |
| `backend/app/config.py` | `agent_max_plan_steps` 等新配置 |
| `backend/app/agent/domain/db/models.py` | 扩展 ORM + 新表 |
| `backend/alembic/versions/<rev>_agent_v2_langgraph.py` | migration |
| `backend/app/agent/domain/plan.py` | `Plan`, `PlanStep` Pydantic |
| `backend/app/agent/domain/sse_v2.py` | SSE v2 类型与枚举 |
| `backend/app/agent/infrastructure/chat_model_factory.py` | `SysModel` → `ChatOpenAI` |
| `backend/app/agent/infrastructure/memory_store.py` | 长期记忆 SQL |
| `backend/app/agent/infrastructure/sse_emitter_v2.py` | `data:` 行序列化 |
| `backend/app/agent/infrastructure/event_mapper.py` | `astream_events` → SSE |
| `backend/app/agent/capabilities/datetime/` | datetime 子 Agent |
| `backend/app/agent/capabilities/file/` | file 子 Agent（复用沙箱） |
| `backend/app/agent/capabilities/general/` | general 子 Agent |
| `backend/app/agent/graphs/state.py` | `AgentGraphState` |
| `backend/app/agent/graphs/nodes/*.py` | 各图节点 |
| `backend/app/agent/graphs/main.py` | `build_main_graph()` |
| `backend/app/agent/service/agent_graph_run_service.py` | Run 编排 + DB + SSE |
| `backend/app/agent/api/v2/router.py` | HTTP v2 |
| `backend/app/agent/api/v2/schemas.py` | Pydantic v2 |
| `backend/app/core/api/router.py` | 注册 v2、移除 v1 |
| `frontend/src/api/agent-v2.ts` | 前端 API |
| `frontend/src/api/agent-stream-v2.ts` | SSE 解析 |
| `frontend/src/features/workspace/AgentsPage.tsx` | UI 改造 |

**删除（Task 14）：** `backend/app/agent/skills/`、`skill_loader.py`、`skill_resolver.py`、`skill_tools.py`、`tool_registry.py`、`service/agent_run_service.py`、`domain/sse_minerva.py`、`domain/openai_chunk.py`、`infrastructure/sse_chunk_emitter.py`、`service/stream_accumulator.py`、`api/router.py`（v1）、`api/schemas.py`（v1）；对应 v1 测试文件。

---

### Task 1: 添加 Python 依赖

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: 在 `[project].dependencies` 追加**

```toml
  "langgraph>=0.2.60",
  "langchain>=0.3.18",
  "langchain-core>=0.3.28",
  "langchain-openai>=0.3.0",
  "langgraph-checkpoint-postgres>=2.0.10",
```

- [ ] **Step 2: 安装依赖**

Run: `cd backend && pip install -e ".[dev]"`

Expected: 无 resolver 错误

- [ ] **Step 3: Commit**

```bash
git add backend/pyproject.toml
git commit -m "chore(agent): add langgraph and langchain dependencies"
```

---

### Task 2: 配置项

**Files:**
- Modify: `backend/app/config.py`

- [ ] **Step 1: 在 `Settings` 中 `agent_max_tool_rounds` 之后追加**

```python
    agent_max_plan_steps: int = Field(
        default=8,
        ge=1,
        description="Planner 单次 run 最大计划步数。",
        validation_alias=AliasChoices("AGENT_MAX_PLAN_STEPS", "agent_max_plan_steps"),
    )
    agent_subagent_recursion_limit: int = Field(
        default=16,
        ge=1,
        description="子 Agent create_react_agent 的 recursion_limit。",
        validation_alias=AliasChoices(
            "AGENT_SUBAGENT_RECURSION_LIMIT",
            "agent_subagent_recursion_limit",
        ),
    )
    agent_memory_retrieve_limit: int = Field(
        default=20,
        ge=1,
        description="长期记忆检索最大条数。",
        validation_alias=AliasChoices(
            "AGENT_MEMORY_RETRIEVE_LIMIT",
            "agent_memory_retrieve_limit",
        ),
    )
    agent_message_fallback_limit: int = Field(
        default=50,
        ge=1,
        description="长期记忆不足时 agent_message fallback 条数。",
        validation_alias=AliasChoices(
            "AGENT_MESSAGE_FALLBACK_LIMIT",
            "agent_message_fallback_limit",
        ),
    )
```

- [ ] **Step 2: 验证加载**

Run: `cd backend && python -c "from app.config import settings; print(settings.agent_max_plan_steps)"`

Expected: `8`

- [ ] **Step 3: Commit**

```bash
git add backend/app/config.py
git commit -m "feat(agent): add langgraph-related settings"
```

---

### Task 3: 领域类型 Plan 与 SSE v2

**Files:**
- Create: `backend/app/agent/domain/plan.py`
- Create: `backend/app/agent/domain/sse_v2.py`
- Create: `backend/tests/test_agent_plan.py`
- Create: `backend/tests/test_agent_sse_v2.py`

- [ ] **Step 1: 写失败测试 `test_agent_plan.py`**

```python
"""Tests for agent Plan models."""

from app.agent.domain.plan import Plan, PlanStep


def test_plan_step_capability_normalized() -> None:
    step = PlanStep(id="1", capability="FILE", goal="list files")
    assert step.capability == "file"


def test_plan_from_json_steps() -> None:
    raw = {
        "steps": [
            {"id": "s1", "capability": "general", "goal": "greet", "status": "pending"}
        ]
    }
    plan = Plan.model_validate(raw)
    assert len(plan.steps) == 1
    assert plan.steps[0].capability == "general"
```

- [ ] **Step 2: 运行测试确认 FAIL**

Run: `cd backend && pytest tests/test_agent_plan.py -v`

Expected: `ModuleNotFoundError` 或 validation 失败

- [ ] **Step 3: 实现 `domain/plan.py`**

```python
"""Structured plan models for Plan-and-Execute agent runs."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

PlanStepStatus = Literal["pending", "running", "success", "failed", "skipped"]
CapabilityName = Literal["general", "file", "datetime"]


class PlanStep(BaseModel):
    """One executable step routed to a sub-agent capability."""

    id: str
    capability: CapabilityName
    goal: str
    status: PlanStepStatus = "pending"
    done_criteria: str | None = None

    @field_validator("capability", mode="before")
    @classmethod
    def _norm_capability(cls, v: object) -> str:
        return str(v).strip().lower()


class Plan(BaseModel):
    """Planner output consumed by the executor node."""

    steps: list[PlanStep] = Field(default_factory=list)
```

- [ ] **Step 4: 写失败测试 `test_agent_sse_v2.py`**

```python
"""Tests for SSE v2 envelope serialization."""

import json

from app.agent.domain.sse_v2 import AgentSseEventType, build_sse_event


def test_build_sse_event_v2() -> None:
    line = build_sse_event(
        event_type=AgentSseEventType.run_started,
        run_id="00000000-0000-0000-0000-000000000001",
        session_id="00000000-0000-0000-0000-000000000002",
        payload={"status": "running"},
    )
    assert line.startswith(b"data: ")
    body = json.loads(line.removeprefix(b"data: ").strip())
    assert body["v"] == 2
    assert body["type"] == "run.started"
```

- [ ] **Step 5: 实现 `domain/sse_v2.py`**

```python
"""SSE v2 event types and serialization for agent runs."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import UUID

import orjson

SSE_DONE_LINE = b"data: [DONE]\n\n"


class AgentSseEventType(str, Enum):
    """Discriminator for agent SSE v2 stream events."""

    run_started = "run.started"
    run_finished = "run.finished"
    run_error = "run.error"
    plan_created = "plan.created"
    plan_step_updated = "plan.step_updated"
    graph_node = "graph.node"
    subagent_started = "subagent.started"
    subagent_finished = "subagent.finished"
    llm_delta = "llm.delta"
    tool_started = "tool.started"
    tool_finished = "tool.finished"
    memory_retrieved = "memory.retrieved"
    message_final = "message.final"


def utc_iso_now() -> str:
    """Return current UTC time as ISO-8601 string."""

    return datetime.now(timezone.utc).isoformat()


def build_sse_event(
    *,
    event_type: AgentSseEventType,
    run_id: UUID | str,
    session_id: UUID | str | None,
    payload: dict[str, Any],
    ts: str | None = None,
) -> bytes:
    """Format one SSE ``data:`` line for agent v2."""

    envelope = {
        "v": 2,
        "type": event_type.value,
        "run_id": str(run_id),
        "session_id": str(session_id) if session_id else None,
        "ts": ts or utc_iso_now(),
        "payload": payload,
    }
    return b"data: " + orjson.dumps(envelope) + b"\n\n"
```

- [ ] **Step 6: 运行测试**

Run: `cd backend && pytest tests/test_agent_plan.py tests/test_agent_sse_v2.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/agent/domain/plan.py backend/app/agent/domain/sse_v2.py \
  backend/tests/test_agent_plan.py backend/tests/test_agent_sse_v2.py
git commit -m "feat(agent): add Plan and SSE v2 domain types"
```

---

### Task 4: ORM 扩展与 Alembic 迁移

**Files:**
- Modify: `backend/app/agent/domain/db/models.py`
- Create: `backend/alembic/versions/<timestamp>_agent_v2_langgraph_tables.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`（确保 import 新模型）

- [ ] **Step 1: 在 `models.py` 增加 `AgentLongTermMemory` 与 `AgentPlan`**

```python
class AgentLongTermMemory(Base):
    """工作区/会话级长期记忆（SQL 检索，首期无向量）。"""

    __tablename__ = "agent_long_term_memory"
    __table_args__ = (
        Index("ix_agent_ltm_workspace_session", "workspace_id", "session_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("workspaces.id", ondelete="CASCADE"), index=True, nullable=False
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_session.id", ondelete="CASCADE"), index=True, nullable=True
    )
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
    source_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AgentPlan(Base):
    """单次 run 的结构化计划快照。"""

    __tablename__ = "agent_plan"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("agent_run.id", ondelete="CASCADE"), index=True, nullable=False
    )
    steps_json: Mapped[dict[str, Any] | list[Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default=sa.text("'active'"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
```

- [ ] **Step 2: 扩展 `AgentSession` / `AgentMessage`**

在 `AgentSession` 增加：

```python
    summary_text: Mapped[str | None] = mapped_column(Text, nullable=True)
```

在 `AgentMessage` 增加：

```python
    message_json: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSONB, nullable=True)
```

- [ ] **Step 3: 生成 migration**

Run: `cd backend && alembic revision --autogenerate -m "agent_v2_langgraph_tables"`

手工检查 revision：包含 `agent_long_term_memory`、`agent_plan`、列变更；**另按** [LangGraph PostgresSaver 文档](https://langchain-ai.github.io/langgraph/how-tos/persistence_postgres/) 调用 `AsyncPostgresSaver.setup()` 或在 migration 中创建 checkpoint 表（`checkpoints`, `checkpoint_blobs`, `checkpoint_writes` 等，以所用 `langgraph-checkpoint-postgres` 版本为准）。

- [ ] **Step 4: 应用 migration（本地 PG）**

Run: `cd backend && alembic upgrade head`

Expected: 成功

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/domain/db/models.py backend/alembic/versions/*agent_v2*
git commit -m "feat(agent): add long-term memory and plan tables"
```

---

### Task 5: MemoryStore（长期记忆 SQL）

**Files:**
- Create: `backend/app/agent/infrastructure/memory_store.py`
- Modify: `backend/app/agent/infrastructure/repository.py`（如需 helper）
- Create: `backend/tests/test_agent_memory_store.py`

- [ ] **Step 1: 写失败测试**

```python
"""Tests for AgentMemoryStore (requires DB fixtures or mocked session)."""

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.infrastructure.memory_store import AgentMemoryStore


@pytest.mark.asyncio
async def test_retrieve_returns_hits_sorted(db_session: AsyncSession) -> None:
    store = AgentMemoryStore()
    ws = uuid.uuid4()
    await store.upsert_fact(
        db_session,
        workspace_id=ws,
        session_id=None,
        key="tz",
        content="user prefers UTC",
        kind="fact",
        tags=["preference"],
    )
    hits = await store.retrieve(
        db_session,
        workspace_id=ws,
        session_id=None,
        query_text="UTC",
        limit=5,
    )
    assert len(hits) >= 1
    assert "UTC" in hits[0].content
```

注：若项目无 `db_session` fixture，在 `tests/conftest.py` 增加 async session fixture（参考其他集成测）。

- [ ] **Step 2: 实现 `memory_store.py`**

核心方法：

- `retrieve(session, *, workspace_id, session_id, query_text, limit)` → `list[MemoryHit]`
  1. `SELECT ... FROM agent_long_term_memory WHERE workspace_id AND (session_id IS NULL OR =) AND (content ILIKE :q OR key ILIKE :q) ORDER BY created_at DESC LIMIT :limit`
  2. 若 `len(hits) < limit`：对 `agent_message` 近 N 条 `content ILIKE` 补充 `MemoryHit(source="message")`
- `upsert_fact(...)` / `insert_summary(...)` 供 `memory.persist` 使用

- [ ] **Step 3: 运行测试**

Run: `cd backend && pytest tests/test_agent_memory_store.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/infrastructure/memory_store.py backend/tests/test_agent_memory_store.py
git commit -m "feat(agent): add SQL long-term memory store"
```

---

### Task 6: ChatModelFactory（SysModel → LangChain）

**Files:**
- Create: `backend/app/agent/infrastructure/chat_model_factory.py`
- Create: `backend/tests/test_agent_chat_model_factory.py`

- [ ] **Step 1: 写失败测试（mock SysModel 行）**

```python
"""Tests for ChatModelFactory."""

import uuid
from unittest.mock import MagicMock

import pytest

from app.agent.infrastructure.chat_model_factory import ChatModelFactory
from app.exceptions import AppError


def test_raises_when_model_disabled() -> None:
    row = MagicMock()
    row.enabled = False
    row.workspace_id = uuid.uuid4()
    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=row.workspace_id)
    assert exc.value.code == "agent.model_disabled"
```

- [ ] **Step 2: 实现工厂**

```python
"""Build LangChain chat models from workspace SysModel rows."""

from __future__ import annotations

import uuid

from langchain_openai import ChatOpenAI

from app.exceptions import AppError
from app.llm.domain.models import ProviderKind
from app.sys.model_provider.domain.db.models import SysModel
from app.sys.model_provider.infrastructure import repository as model_repo


class ChatModelFactory:
    """Resolve ``SysModel`` into a LangChain ``ChatOpenAI`` (or provider-specific) instance."""

    @staticmethod
    def from_sys_model_row(row: SysModel, *, workspace_id: uuid.UUID) -> ChatOpenAI:
        """Validate workspace ownership and enabled flag, then construct the client."""

        if row.workspace_id != workspace_id:
            raise AppError("agent.model_not_found", "模型不存在或不属于当前工作区。")
        if not row.enabled:
            raise AppError("agent.model_disabled", "模型未启用。")
        base_url = (row.endpoint_url or "").strip()
        if not base_url:
            raise AppError("agent.model_misconfigured", "模型缺少 endpoint_url。")
        api_key = (row.api_key or "").strip()
        if not api_key:
            raise AppError("agent.model_misconfigured", "模型缺少 api_key。")
        # Map model_type → openai-compatible base; extend for volcengine/aliyun later.
        return ChatOpenAI(
            model=row.model_name,
            base_url=base_url.rstrip("/"),
            api_key=api_key,
            temperature=0.7,
        )

    @staticmethod
    async def get(session, *, workspace_id: uuid.UUID, model_id: uuid.UUID) -> ChatOpenAI:
        """Load ``SysModel`` from DB and return a chat model."""

        row = await model_repo.get_by_id(session, model_id=model_id, workspace_id=workspace_id)
        if row is None:
            raise AppError("agent.model_not_found", "模型不存在或不属于当前工作区。")
        return ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)
```

- [ ] **Step 3: 运行测试并 Commit**

---

### Task 7: Capability `datetime` 子 Agent

**Files:**
- Create: `backend/app/agent/capabilities/datetime/tools.py`
- Create: `backend/app/agent/capabilities/datetime/prompt.py`
- Create: `backend/app/agent/capabilities/datetime/agent.py`
- Create: `backend/tests/test_agent_capability_datetime.py`

- [ ] **Step 1: 从 `skills/system_datetime/tools.py` 迁移为 `@tool`**

```python
from langchain_core.tools import tool

@tool
def get_system_datetime(timezone: str = "UTC") -> str:
    """返回服务器当前日期时间（ISO-8601 JSON）。"""
    ...
```

- [ ] **Step 2: `agent.py` 暴露 `build_datetime_react_agent(model: ChatOpenAI)`**

```python
from langgraph.prebuilt import create_react_agent

def build_datetime_react_agent(model):
    return create_react_agent(model, tools=[get_system_datetime])
```

- [ ] **Step 3: 单测：invoke 工具返回 JSON 含 `iso`**

- [ ] **Step 4: Commit**

---

### Task 8: Capability `file` 子 Agent

**Files:**
- Create: `backend/app/agent/capabilities/file/tools.py`
- Create: `backend/app/agent/capabilities/file/prompt.py`
- Create: `backend/app/agent/capabilities/file/agent.py`
- Modify: 保留 `backend/app/agent/infrastructure/agent_file_sandbox.py`（不改逻辑）

- [ ] **Step 1: 将 `skills/file/tools.py` 六个 handler 改为 `@tool`，首参通过 `InjectedToolArg` 或闭包绑定 `workspace_id`**

推荐：在 `build_file_react_agent(model, workspace_id)` 内定义带 `workspace_id` 闭包的 tools，避免全局状态。

- [ ] **Step 2: 复用 `AgentFileSandbox`；错误返回 JSON 字符串（与现行为一致）**

- [ ] **Step 3: 运行现有沙箱测试**

Run: `cd backend && pytest tests/test_agent_file_sandbox.py -v`

Expected: PASS（沙箱未破坏）

- [ ] **Step 4: Commit**

---

### Task 9: Capability `general` 子 Agent

**Files:**
- Create: `backend/app/agent/capabilities/general/prompt.py`
- Create: `backend/app/agent/capabilities/general/agent.py`

- [ ] **Step 1: `build_general_react_agent(model)` — `tools=[]` 或极简工具**

- [ ] **Step 2: Commit**

---

### Task 10: LangGraph 状态与节点

**Files:**
- Create: `backend/app/agent/graphs/state.py`
- Create: `backend/app/agent/graphs/nodes/memory_retrieve.py`
- Create: `backend/app/agent/graphs/nodes/memory_persist.py`
- Create: `backend/app/agent/graphs/nodes/planner.py`
- Create: `backend/app/agent/graphs/nodes/executor.py`
- Create: `backend/app/agent/graphs/nodes/synthesizer.py`
- Create: `backend/app/agent/graphs/nodes/subagents.py`

- [ ] **Step 1: 定义 `AgentGraphState`（TypedDict，`messages` 使用 `Annotated[list, add_messages]`）**

- [ ] **Step 2: `planner` 节点**

使用 `model.with_structured_output(Plan)` 或 JSON prompt + `Plan.model_validate_json`；输入：`user_message`、`retrieved_memories`、capabilities 列表；输出：写入 `state["plan"]` 并 `repository.create_agent_plan`。

- [ ] **Step 3: `executor` 节点**

读取 `plan.steps[current_step_index]`；`capability` → 调用对应 compiled subagent；`ainvoke` 结果 append 到 `subagent_results`；`current_step_index += 1`；发 SSE `plan.step_updated`（在 service 层或节点内通过 callback）。

- [ ] **Step 4: 条件边 `should_continue_executor`**

若 `current_step_index < len(plan.steps)` → `executor`；否则 → `synthesizer`。

- [ ] **Step 5: `memory.retrieve` / `memory.persist` 调用 `AgentMemoryStore`**

- [ ] **Step 6: Commit**

---

### Task 11: 编译主图 + PostgresSaver

**Files:**
- Create: `backend/app/agent/graphs/main.py`
- Create: `backend/tests/test_agent_graph_compile.py`

- [ ] **Step 1: `build_main_graph(*, checkpointer)` 注册节点与边（见 spec §3.2）**

```python
from langgraph.graph import StateGraph, START, END

def build_main_graph(checkpointer):
    g = StateGraph(AgentGraphState)
    g.add_node("memory.retrieve", memory_retrieve_node)
    g.add_node("planner", planner_node)
    ...
    g.add_edge(START, "memory.retrieve")
    g.add_edge("memory.retrieve", "planner")
    g.add_edge("planner", "executor")
    g.add_conditional_edges("executor", route_after_executor, ...)
    g.add_edge("synthesizer", "memory.persist")
    g.add_edge("memory.persist", END)
    return g.compile(checkpointer=checkpointer)
```

- [ ] **Step 2: 在测试中 `compile()` 不连真实 PG（`checkpointer=None`）断言节点名存在**

- [ ] **Step 3: 在 `AgentGraphRunService` 初始化时 `AsyncPostgresSaver.from_conn_string(DATABASE_URL)` + `setup()`**

- [ ] **Step 4: Commit**

---

### Task 12: SSE v2 EventMapper 与 GraphRunService

**Files:**
- Create: `backend/app/agent/infrastructure/event_mapper.py`
- Create: `backend/app/agent/service/agent_graph_run_service.py`
- Create: `backend/tests/test_agent_event_mapper.py`

- [ ] **Step 1: `AgentGraphEventMapper.map_event(lc_event) -> bytes | None`**

处理至少：

- `on_chat_model_stream` → `llm.delta`（`channel` 来自 `reasoning_content` / `content`）
- `on_tool_start` / `on_tool_end` → `tool.started` / `tool.finished`
- 自定义 `on_chain_start` 带 `name` 前缀 `subagent:` → `subagent.started`

- [ ] **Step 2: `AgentGraphRunService.run_stream_sse` 骨架**

```python
async def run_stream_sse(self, session, *, run_id, workspace_id, user_id, session_id, user_message, model_id, ...):
    yield build_sse_event(event_type=AgentSseEventType.run_started, ...)
    model = await ChatModelFactory.get(session, workspace_id=workspace_id, model_id=model_id)
    graph = build_main_graph(checkpointer=self._checkpointer)
    config = {"configurable": {"thread_id": f"{session_id}:{run_id}"}}
    async for ev in graph.astream_events(initial_state, config=config, version="v2"):
        if chunk := self._mapper.map_event(ev):
            yield chunk
    yield SSE_DONE_LINE
```

- [ ] **Step 3: 集成 DB：create run、append user message、insert_run_node、finalize**

- [ ] **Step 4: 写 mapper 单测（构造假 `lc_event` dict）**

- [ ] **Step 5: Commit**

---

### Task 13: API v2 路由

**Files:**
- Create: `backend/app/agent/api/v2/schemas.py`
- Create: `backend/app/agent/api/v2/router.py`
- Modify: `backend/app/core/api/router.py`
- Create: `backend/tests/test_agent_api_v2.py`

- [ ] **Step 1: `AgentRunCreateV2`：`user_message`, `model_id`, `temperature?`, `max_tokens?`, `preferred_capabilities?`**

- [ ] **Step 2: 路由前缀 `/workspaces/{workspace_id}/agent/v2`**

会话 CRUD 与 v1 相同路径结构；`GET /capabilities` 返回 `[{id, description}]`；`POST /sessions/{id}/runs` → `StreamingResponse`。

- [ ] **Step 3: 在 `core/api/router.py` 替换**

```python
from app.agent.api.v2.router import router as agent_router
```

- [ ] **Step 4: 更新 auth 测试路径**

```python
async def test_agent_v2_create_run_requires_auth():
    res = await ac.post(
        f"/workspaces/{ws}/agent/v2/sessions/{sid}/runs",
        json={"user_message": "hi", "model_id": str(uuid.uuid4())},
    )
    assert res.status_code == 401
```

- [ ] **Step 5: Commit**

---

### Task 14: 删除 v1 代码与测试

**Files:**
- Delete: 见 File map「删除」列表
- Modify: `backend/tests/` 移除或重写 v1 专用测试

- [ ] **Step 1: 删除 `backend/app/agent/skills/` 整个目录**

- [ ] **Step 2: 删除 v1 infrastructure/service/api 文件**

- [ ] **Step 3: 删除/替换测试**

| 删除 | 替代 |
|------|------|
| `test_agent_sse_openai_format.py` | `test_agent_sse_v2.py` |
| `test_agent_stream_accumulator.py` | （由 event mapper 覆盖） |
| `test_skill_*.py` | capability 测试 |
| `test_agent_api.py` | `test_agent_api_v2.py` |

- [ ] **Step 4: 全量 pytest**

Run: `cd backend && pytest tests/ -v --ignore=tests/e2e`

Expected: PASS（允许跳过需真实 LLM 的集成测，使用 `@pytest.mark.integration`）

- [ ] **Step 5: Commit**

```bash
git commit -m "refactor(agent): remove v1 skill loader and OpenAI SSE adapter"
```

---

### Task 15: 前端 SSE v2 与 AgentsPage

**Files:**
- Create: `frontend/src/api/agent-stream-v2.ts`
- Create: `frontend/src/api/agent-v2.ts`
- Modify: `frontend/src/features/workspace/AgentsPage.tsx`
- Modify: `frontend/src/app/router.tsx`（若路径变）
- Delete or stop using: `frontend/src/api/agent.ts` 中 v1 run 逻辑（可删文件若全无引用）

- [ ] **Step 1: `agent-stream-v2.ts` 解析 `v===2` 事件**

```typescript
export type AgentSseEventV2 = {
  v: 2
  type: string
  run_id: string
  session_id?: string
  ts: string
  payload: Record<string, unknown>
}

export function parseAgentV2SseLine(raw: string): AgentSseEventV2 | 'done' | null
```

- [ ] **Step 2: `agent-v2.ts` — `streamAgentRunV2(workspaceId, sessionId, { user_message, model_id })`**

不再发送 `api_key` / `base_url`；`model_id` 来自 `selectedModelId`。

- [ ] **Step 3: `AgentsPage` 状态机**

- `planSteps` 来自 `plan.created` / `plan.step_updated`
- `reasoningText` 累积 `llm.delta` where `channel==='reasoning'`
- `assistantText` 累积 `channel==='assistant'`
- `toolLog[]` 来自 `tool.started` / `tool.finished`
- 移除 `agentSkillUi` 的 `/file` 前缀逻辑；可选 capabilities 多选写入 `preferred_capabilities`

- [ ] **Step 4: 手动验证**

启动前后端 → 选模型 → 发送「现在几点」→ 应看到 plan + datetime 子 agent + 最终回复。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/agent-v2.ts frontend/src/api/agent-stream-v2.ts \
  frontend/src/features/workspace/AgentsPage.tsx
git commit -m "feat(ui): agent v2 SSE and planner trace UI"
```

---

### Task 16: 更新 spec 状态与文档

**Files:**
- Modify: `docs/superpowers/specs/2026-05-16-agent-langgraph-redesign-design.md`（`状态：已定稿`）

- [ ] **Step 1: 将 spec 状态改为「已定稿」**

- [ ] **Step 2: 在 `docs/ai-api.md` 或 README 增加 Agent v2 小节（可选，1 段说明 SSE 事件表）**

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: mark agent langgraph redesign spec as finalized"
```

---

## Plan self-review（相对 spec）

| Spec 章节 | 覆盖任务 |
|-----------|----------|
| Plan-and-Execute | Task 10–11 |
| 子 Agent ×3 | Task 7–9 |
| Memory 长/短 | Task 4–5, 10 |
| SSE v2 | Task 3, 12, 15 |
| API v2 + model_id | Task 6, 13 |
| 删除 skills | Task 14 |
| 前端 | Task 15 |
| Checkpoint | Task 4, 11 |

无 TBD；类型名 `Plan`/`AgentSseEventType` 全文一致。

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-05-16-agent-langgraph-redesign.md`。

**1. Subagent-Driven（推荐）** — 每 Task 派发子 agent，任务间你做 review  

**2. Inline Execution** — 本会话用 executing-plans 按 Task 批量执行并设检查点  

你更倾向哪一种？
