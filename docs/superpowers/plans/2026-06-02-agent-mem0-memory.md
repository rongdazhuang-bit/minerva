# Agent mem0 记忆双后端 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agent 长期记忆支持 `AGENT_MEMORY_BACKEND=sql|mem0` 互斥切换；mem0 路径使用 pgvector（`minerva_memory`）+ Neo4j 双存储、策略模式分离召回/持久化，并提供 mem0 专属画像管理与 Celery 压缩。

**Architecture:** 新增 `app/agent/memory/` 包：`MemoryRetrieveStrategy` / `MemoryPersistStrategy` + 工厂；SQL 实现包装现有 `AgentMemoryStore` 与 `invoke_memory_extract`；mem0 实现封装 `Memory.from_config`（独立 `MEM0_*` 环境变量）。`GraphDeps` 注入双策略；`memory_retrieve_node` 调用 `build_planner_context`。持久画像表 `agent_memory_profile` 仅 mem0 模式使用。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, LangGraph, mem0ai[graph]>=0.1.117, pgvector, Neo4j, Celery, React 18, Ant Design, pytest.

**Spec:** `docs/superpowers/specs/2026-06-02-agent-mem0-memory-design.md`

---

## Scope Check

单计划、可分期交付：

| 阶段 | 交付物 | 可独立验证 |
|------|--------|------------|
| A | 配置 + SQL 补丁 + 策略骨架 + SQL 后端 + 图接入 | `backend=sql` 回归通过 |
| B | mem0 client + mem0 策略 + 画像 Run 注入 | `backend=mem0` 本地 Run |
| C | 管理 API + 前端 + Celery | mem0 管理页 + beat |
| D | 文档回填 | spec 实现对照 |

---

## File Structure

### Backend — 新建

| 路径 | 职责 |
|------|------|
| `backend/app/agent/memory/protocols.py` | `MemoryRetrieveStrategy` / `MemoryPersistStrategy` Protocol |
| `backend/app/agent/memory/hits.py` | `MemoryHit` dataclass |
| `backend/app/agent/memory/factory.py` | `create_memory_strategies()` |
| `backend/app/agent/memory/sql/retrieve.py` | SQL 召回 |
| `backend/app/agent/memory/sql/persist.py` | SQL 持久化 |
| `backend/app/agent/memory/mem0/client.py` | mem0 配置与单例 |
| `backend/app/agent/memory/mem0/retrieve.py` | mem0 召回 + `build_planner_context` |
| `backend/app/agent/memory/mem0/persist.py` | mem0 `add` |
| `backend/app/agent/memory/mem0/profile_runtime.py` | 现场 session 画像 |
| `backend/app/agent/memory/profile/repository.py` | `agent_memory_profile` CRUD |
| `backend/app/agent/memory/profile/service.py` | 画像业务 |
| `backend/app/agent/domain/db/memory_profile_models.py` | ORM（或并入 `models.py`） |
| `backend/app/agent/api/v2/memory_router.py` | 记忆/画像 API |
| `backend/app/agent/task/memory_compress_job.py` | Celery 压缩 |
| `backend/app/agent/constants.py` | 任务名常量（若尚无则追加） |
| `backend/sql/patches/2026-06-02-agent-memory-profile.sql` | 画像表 |
| `backend/tests/test_agent_memory_factory.py` | 工厂单测 |
| `backend/tests/test_agent_memory_sql_strategy.py` | SQL 策略单测 |
| `backend/tests/test_agent_memory_profile_repo.py` | 画像 repo |
| `backend/tests/test_agent_memory_api.py` | API（mem0 disabled → 404） |

### Backend — 修改

| 路径 | 变更 |
|------|------|
| `backend/pyproject.toml` | `mem0ai[graph]>=0.1.117` |
| `backend/app/config.py` | 全部 `AGENT_MEMORY_*` / `MEM0_*` + `@model_validator` |
| `backend/.env.example`, `backend/.env.dev` | 同步 env |
| `backend/app/agent/infrastructure/memory_store.py` | 保留，供 SQL 策略内部调用 |
| `backend/app/agent/graphs/deps.py` | 双策略字段 |
| `backend/app/agent/graphs/nodes/memory_nodes.py` | 调 retrieve + context |
| `backend/app/agent/graphs/nodes/planner.py` | 优先 `state["memory_context"]` |
| `backend/app/agent/graphs/state.py` | 可选 `memory_context: str` |
| `backend/app/agent/service/memory_persist_service.py` | 委托 `MemoryPersistStrategy` |
| `backend/app/agent/service/agent_graph_run_service.py` | 工厂缓存 + deps 注入 |
| `backend/app/agent/api/v2/router.py` | `include_router(memory_router)` |
| `backend/app/agent/api/v2/schemas.py` | 画像/记忆 schema |
| `backend/app/celery_app.py` | `include` memory_compress 模块 |
| `backend/sql/schema_postgresql.sql` | 追加 `agent_memory_profile`（与 patch 一致） |

### Frontend — 修改/新建

| 路径 | 变更 |
|------|------|
| `frontend/src/api/agent.ts` | memory API 客户端 |
| `frontend/src/features/agent/AgentMemoryPage.tsx` | 新建：画像 + 记忆列表 |
| `frontend/src/features/agent/AgentsPage.tsx` 或路由 | 入口/菜单（`memory_backend===mem0'`） |
| `frontend/src/i18n/locales/zh-CN.json`, `en.json` | 文案 |

### Docs

| 路径 | 变更 |
|------|------|
| `docs/agent-module-design.md` | §8 双后端 |
| `docs/superpowers/specs/2026-06-02-agent-mem0-memory-design.md` | 状态 + 实现对照 |

---

## Task 1: Settings 与环境变量

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`
- Create: `backend/tests/test_agent_memory_settings.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_agent_memory_settings.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.config import Settings


def test_agent_memory_backend_defaults_sql(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.delenv("AGENT_MEMORY_BACKEND", raising=False)
  s = Settings(_env_file=None)
  assert s.agent_memory_backend == "sql"


def test_mem0_backend_requires_pg_config(monkeypatch: pytest.MonkeyPatch) -> None:
  monkeypatch.setenv("AGENT_MEMORY_BACKEND", "mem0")
  monkeypatch.delenv("MEM0_DATABASE_URL", raising=False)
  monkeypatch.delenv("MEM0_PG_HOST", raising=False)
  with pytest.raises(ValidationError):
    Settings(_env_file=None)
```

- [ ] **Step 2: 运行确认 FAIL**

```bash
cd backend && pytest tests/test_agent_memory_settings.py -v
```

- [ ] **Step 3: 在 `Settings` 增加字段**

在 `backend/app/config.py` 的 Agent 配置段后追加（名称与 spec §5.2 一致）：

- `agent_memory_backend: Literal["sql", "mem0"] = "sql"`，`validation_alias=AGENT_MEMORY_BACKEND`
- `mem0_database_url`, `mem0_pg_host`, `mem0_pg_port`, `mem0_pg_user`, `mem0_pg_password`, `mem0_pg_dbname`（默认 `minerva_memory`）
- `mem0_vector_collection`, `mem0_embedding_dims`, `mem0_pg_pool_min`, `mem0_pg_pool_max`
- `mem0_graph_enabled: bool = True`
- `mem0_neo4j_url`, `mem0_neo4j_username`, `mem0_neo4j_password`, `mem0_neo4j_database`, `mem0_neo4j_base_label: bool | None`
- `mem0_llm_provider`, `mem0_llm_model`, `mem0_llm_api_key`, `mem0_llm_base_url`
- `mem0_embedder_provider`, `mem0_embedder_model`, `mem0_embedder_api_key`, `mem0_embedder_base_url`
- `agent_memory_llm_compress_enabled: bool = False`
- `agent_memory_profile_llm_enabled: bool = False`
- `agent_memory_compress_celery_enabled: bool = False`
- `agent_memory_compress_cron: str | None = None`
- `agent_memory_compress_max_age_days: int = 90`

`@model_validator(mode="after")`：

- 若 `agent_memory_backend == "mem0"`：要求 `mem0_database_url` 非空 **或** (`mem0_pg_host` 且 `mem0_pg_user` 且 `mem0_pg_password`)
- 若 `mem0_graph_enabled`：要求 `mem0_neo4j_url` 与 `mem0_neo4j_password`

- [ ] **Step 4: 同步 `.env.example` / `.env.dev`**

注释块示例（值用 dev 占位）：

```env
AGENT_MEMORY_BACKEND=sql
# MEM0_DATABASE_URL=postgresql://minerva:minerva@127.0.0.1:5432/minerva_memory
# MEM0_NEO4J_URL=neo4j://127.0.0.1:7687
# MEM0_GRAPH_ENABLED=true
```

- [ ] **Step 5: pytest PASS**

```bash
cd backend && pytest tests/test_agent_memory_settings.py -v
```

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_agent_memory_settings.py
git commit -m "feat(agent): add mem0 memory backend settings and validation"
```

---

## Task 2: `agent_memory_profile` 表与 ORM

**Files:**
- Create: `backend/sql/patches/2026-06-02-agent-memory-profile.sql`
- Modify: `backend/sql/schema_postgresql.sql`
- Modify: `backend/app/agent/domain/db/models.py`（或独立 model 文件）
- Create: `backend/tests/test_agent_memory_profile_repo.py`

- [ ] **Step 1: SQL 补丁（无 FK）**

```sql
-- backend/sql/patches/2026-06-02-agent-memory-profile.sql
CREATE TABLE IF NOT EXISTS agent_memory_profile (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL,
    session_id UUID,
    profile_text TEXT NOT NULL DEFAULT '',
    updated_by UUID,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_agent_memory_profile_workspace
    ON agent_memory_profile (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_memory_profile_workspace_session
    ON agent_memory_profile (workspace_id, session_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_profile_workspace_null_session
    ON agent_memory_profile (workspace_id) WHERE session_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_agent_memory_profile_workspace_session
    ON agent_memory_profile (workspace_id, session_id) WHERE session_id IS NOT NULL;
```

- [ ] **Step 2: ORM `AgentMemoryProfile`**

```python
class AgentMemoryProfile(Base):
    __tablename__ = "agent_memory_profile"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True, nullable=True)
    profile_text: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("now()"), nullable=False)
```

- [ ] **Step 3: repository 函数 + 单测**（`get_workspace_profile`, `get_session_profile`, `upsert`, `list`, `delete`）

- [ ] **Step 4: Commit**

```bash
git add backend/sql/patches/2026-06-02-agent-memory-profile.sql backend/sql/schema_postgresql.sql backend/app/agent/domain/db/models.py backend/app/agent/memory/profile/repository.py backend/tests/test_agent_memory_profile_repo.py
git commit -m "feat(agent): add agent_memory_profile table and repository"
```

---

## Task 3: Protocol、MemoryHit、工厂

**Files:**
- Create: `backend/app/agent/memory/hits.py`
- Create: `backend/app/agent/memory/protocols.py`
- Create: `backend/app/agent/memory/factory.py`
- Create: `backend/tests/test_agent_memory_factory.py`

- [ ] **Step 1: MemoryHit**

```python
# backend/app/agent/memory/hits.py
@dataclass(frozen=True)
class MemoryHit:
    content: str
    kind: str
    source: str
    key: str | None = None
    memory_id: uuid.UUID | str | None = None
    score: float | None = None
```

- [ ] **Step 2: protocols + factory**

```python
# factory.py
def create_memory_strategies() -> tuple[MemoryRetrieveStrategy, MemoryPersistStrategy]:
    if settings.agent_memory_backend == "mem0":
        from app.agent.memory.mem0.retrieve import Mem0MemoryRetrieveStrategy
        from app.agent.memory.mem0.persist import Mem0MemoryPersistStrategy
        return Mem0MemoryRetrieveStrategy(), Mem0MemoryPersistStrategy()
    from app.agent.memory.sql.retrieve import SqlMemoryRetrieveStrategy
    from app.agent.memory.sql.persist import SqlMemoryPersistStrategy
    return SqlMemoryRetrieveStrategy(), SqlMemoryPersistStrategy()
```

- [ ] **Step 3: 单测 mock settings**

```python
def test_factory_returns_sql_pair(monkeypatch):
    monkeypatch.setattr("app.agent.memory.factory.settings.agent_memory_backend", "sql")
    r, p = create_memory_strategies()
    assert type(r).__name__ == "SqlMemoryRetrieveStrategy"
```

- [ ] **Step 4: Commit**

---

## Task 4: SQL 策略（包装现有逻辑）

**Files:**
- Create: `backend/app/agent/memory/sql/retrieve.py`
- Create: `backend/app/agent/memory/sql/persist.py`
- Modify: `backend/app/agent/infrastructure/memory_store.py` — 从 `hits` re-export `MemoryHit` 或保留兼容别名
- Create: `backend/tests/test_agent_memory_sql_strategy.py`

- [ ] **Step 1: SqlMemoryRetrieveStrategy**

- 构造注入 `AgentMemoryStore()`（或 session 由方法参数传入：retrieve 签名与 Protocol 一致，内部 `async with` 不需要——使用 `deps.db` 由调用方传入；**调整 Protocol**：retrieve/persist 增加 `session: AsyncSession` 参数，与现网一致）

**Protocol 修订（实现 Task 3 时同步）：**

```python
async def retrieve(self, session: AsyncSession, *, workspace_id: UUID, ...) -> list[MemoryHit]: ...
async def persist_turn(self, session: AsyncSession, *, workspace_id: UUID, ...) -> None: ...
```

- `retrieve`：调用 `memory_store.retrieve(session, ...)`
- `build_planner_context`：仅格式化 hits（`memory_context_text` 逻辑），**不**读画像表

- [ ] **Step 2: SqlMemoryPersistStrategy**

- 将 `persist_turn_memory` 主体迁入，`model` 必填；保留 run_node 与 usage 逻辑

- [ ] **Step 3: 回归** `pytest tests/test_agent_memory_persist_usage.py -v`（暂仍用旧入口时需先 Task 5 接好）

- [ ] **Step 4: Commit**

---

## Task 5: GraphDeps 与 memory 节点接入

**Files:**
- Modify: `backend/app/agent/graphs/deps.py`
- Modify: `backend/app/agent/graphs/state.py`
- Modify: `backend/app/agent/graphs/nodes/memory_nodes.py`
- Modify: `backend/app/agent/graphs/nodes/planner.py`
- Modify: `backend/app/agent/service/agent_graph_run_service.py`
- Modify: `backend/app/agent/service/memory_persist_service.py`

- [ ] **Step 1: GraphDeps**

```python
memory_retrieve: MemoryRetrieveStrategy
memory_persist: MemoryPersistStrategy
```

- [ ] **Step 2: memory_retrieve_node**

```python
hits = await deps.memory_retrieve.retrieve(
    deps.db,
    workspace_id=deps.workspace_id,
    session_id=deps.session_id,
    query_text=state.get("user_message", ""),
)
context = await deps.memory_retrieve.build_planner_context(
    deps.db,
    workspace_id=deps.workspace_id,
    session_id=deps.session_id,
    query_text=state.get("user_message", ""),
    hits=hits,
)
payload = {
    "hit_count": len(hits),
    "sources": [h.source for h in hits[:5]],
    "backend": settings.agent_memory_backend,
    "degraded": False,
}
return {"retrieved_memories": hits, "memory_context": context, ...}
```

- [ ] **Step 3: planner** — `memory_context_text(state)` 优先返回 `state.get("memory_context") or ...`

- [ ] **Step 4: AgentGraphRunService**

```python
self._memory_retrieve, self._memory_persist = create_memory_strategies()
# deps 构造传入二者
```

- [ ] **Step 5: memory_persist_service** — `schedule_persist_turn_memory_background` 使用 `create_memory_strategies()[1]`

- [ ] **Step 6: 全量 sql 回归**

```bash
cd backend && pytest tests/test_agent_memory_persist_usage.py tests/test_agent_memory_factory.py -v
```

- [ ] **Step 7: Commit**

---

## Task 6: mem0 依赖与 client

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/app/agent/memory/mem0/client.py`

- [ ] **Step 1: 添加依赖**

```toml
"mem0ai[graph]>=0.1.117",
```

```bash
cd backend && pip install -e ".[dev]"
```

- [ ] **Step 2: `build_mem0_config() -> dict`**

从 `settings` 组装 spec §5.1；`mem0_graph_enabled=False` 时省略 `graph_store`。

- [ ] **Step 3: 单例**

```python
_memory: Memory | None = None

def get_mem0_memory() -> Memory:
    global _memory
    if _memory is None:
        from mem0 import Memory
        _memory = Memory.from_config(build_mem0_config())
    return _memory
```

- [ ] **Step 4: Commit**

---

## Task 7: Mem0 召回与持久化策略

**Files:**
- Create: `backend/app/agent/memory/mem0/retrieve.py`
- Create: `backend/app/agent/memory/mem0/persist.py`
- Create: `backend/app/agent/memory/mem0/profile_runtime.py`

- [ ] **Step 1: retrieve — `asyncio.to_thread` 包装 sync mem0**

```python
def _search_sync(...):
    m = get_mem0_memory()
    return m.search(
        query_text,
        user_id=str(workspace_id),
        run_id=str(session_id),
        limit=cap,
        rerank=True,
    )

async def retrieve(...):
    try:
        raw = await asyncio.to_thread(_search_sync, ...)
    except Exception:
        log.warning("mem0 search failed", exc_info=True)
        return []
    # map results -> MemoryHit(source="mem0", memory_id=row["id"], score=...)
```

- [ ] **Step 2: build_planner_context**

1. `profile_service.get_layers(session, workspace_id, session_id)` → workspace + session 文本  
2. `build_runtime_session_profile(...)` — search 拼接；若 `agent_memory_profile_llm_enabled` 再 LLM（用 mem0 配置的 OpenAI 客户端，非 ChatModelFactory）  
3. 格式化 hits  
4. 拼接段落标题：`## 工作区画像` / `## 会话画像` / `## 本轮上下文` / `## 相关记忆`

- [ ] **Step 3: persist**

```python
messages = [
    {"role": "user", "content": user_message},
    {"role": "assistant", "content": final_answer},
]
await asyncio.to_thread(
    lambda: get_mem0_memory().add(
        messages,
        user_id=str(workspace_id),
        run_id=str(session_id),
        infer=True,
        metadata={"source_run_id": str(run_id)},
    )
)
```

- 保留 `memory.persist` run_node；mem0 路径无 `invoke_memory_extract` 时可不写 `llm.round` 子节点

- [ ] **Step 4: 手动冒烟**（需本地 minerva_memory + Neo4j）

```bash
# .env.local 设 AGENT_MEMORY_BACKEND=mem0 与各 MEM0_*
# 发起一次 agent run，检查 memory.retrieved SSE
```

- [ ] **Step 5: Commit**

---

## Task 8: 管理 API（mem0 专属）

**Files:**
- Create: `backend/app/agent/api/v2/memory_router.py`
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`
- Create: `backend/tests/test_agent_memory_api.py`

- [ ] **Step 1: 依赖检查装饰器**

```python
def require_mem0_backend() -> None:
    if settings.agent_memory_backend != "mem0":
        raise AppError(404, "agent.memory_backend_disabled", "Memory API requires mem0 backend")
```

- [ ] **Step 2: 路由**（spec §7.1）+ Popconfirm 仅前端；后端 DELETE 直接删

- [ ] **Step 3: GET `/agent/v2/config` 或扩展现有 session 列表响应** — 增加 `memory_backend: str`

- [ ] **Step 4: API 测试** — `backend=sql` 时 `GET .../memory/profiles` → 404

- [ ] **Step 5: Commit**

---

## Task 9: Celery 压缩任务

**Files:**
- Create: `backend/app/agent/task/memory_compress_job.py`
- Modify: `backend/app/agent/constants.py`
- Modify: `backend/app/celery_app.py` — autodiscover
- 文档：在 `.env.example` 说明需在 `sys_celery` 插入任务行（若 beat 来自 DB）

- [ ] **Step 1: 常量**

```python
AGENT_MEMORY_COMPRESS_TASK_NAME = "agent.memory.compress_mem0"
```

- [ ] **Step 2: 任务实现**

```python
@shared_task(bind=True, name=AGENT_MEMORY_COMPRESS_TASK_NAME)
@scheduled_singleton_guard
def compress_mem0_memories(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    if settings.agent_memory_backend != "mem0" or not settings.agent_memory_compress_celery_enabled:
        return {"skipped": True}
    # 遍历 workspace/session：get_all -> 按 created_at 过滤 -> LLM 摘要 -> add + delete
```

- [ ] **Step 3: `config.py` 启动时** — 若 `agent_memory_compress_celery_enabled` 且缺 `agent_memory_compress_cron`，打 warning（beat 行由运维插入 `sys_celery`）

- [ ] **Step 4: Commit**

---

## Task 10: 前端记忆管理页

**Files:**
- Modify: `frontend/src/api/agent.ts`
- Create: `frontend/src/features/agent/AgentMemoryPage.tsx`
- Modify: 路由配置（`frontend/src` 内 agent 路由文件）
- Modify: `frontend/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1: API 类型与函数** — `listMemoryProfiles`, `patchMemoryProfile`, `listMem0Memories`, `deleteMem0Memory`, `getAgentV2Config`

- [ ] **Step 2: 页面** — Tabs：画像（工作区/会话 selector）+ 记忆列表 Table；删除用 `Popconfirm`

- [ ] **Step 3: 菜单** — 读取 `memory_backend`，非 `mem0` 不渲染入口

- [ ] **Step 4: Commit**

---

## Task 11: 文档与 spec 回填

**Files:**
- Modify: `docs/agent-module-design.md`
- Modify: `docs/superpowers/specs/2026-06-02-agent-mem0-memory-design.md`

- [ ] **Step 1:** §8 增加双后端、env、部署（minerva_memory + Neo4j APOC）

- [ ] **Step 2:** spec 状态 → 已实现；§10 实现对照填路径

- [ ] **Step 3: Commit**

```bash
git add docs/agent-module-design.md docs/superpowers/specs/2026-06-02-agent-mem0-memory-design.md
git commit -m "docs(agent): document mem0 memory dual-backend"
```

---

## Plan Self-Review

| Spec 章节 | 任务 |
|-----------|------|
| 互斥切换 | Task 1, 3, 5 |
| 双 Protocol | Task 3–5 |
| pgvector + Neo4j | Task 1, 6–7 |
| 会话级隔离 | Task 7 |
| 画像分层 | Task 2, 7, 8, 10 |
| LLM 压缩默认关 | Task 1, 7 |
| Celery mem0 专属 | Task 9 |
| 管理端 mem0 专属 | Task 8, 10 |
| SQL 回归 | Task 4–5 |
| env 同步 | Task 1 |
| 无 FK | Task 2 |
| SSE degraded | Task 5, 7 |

无 TBD；Protocol 已明确 `session: AsyncSession` 参数（与现 `AgentMemoryStore` 一致）。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-02-agent-mem0-memory.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每 Task 派发子 agent，Task 间你做 review  
2. **Inline Execution** — 本会话按 Task 顺序实现，批次间设检查点  

你更倾向哪一种？回复 `1` 或 `2`（或指定从 Task N 开始）即可开始实现。
