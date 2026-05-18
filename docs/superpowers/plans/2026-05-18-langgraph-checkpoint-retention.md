# LangGraph Checkpoint 保留清理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 LangGraph checkpoint 三表增加 `create_at`/`update_at`（含触发器与索引），并通过可配置保留天数 + `sys_celery` 调度的 Celery 任务分批清理过期行。

**Architecture:** DDL 写入 `schema_postgresql.sql`（新库）与 `agent_v2_langgraph_migration.sql`（存量 `ALTER`）；清理逻辑在 `checkpoint_purge_service`（同步 SQL + advisory lock）；Celery 任务 `agent.checkpoint_purge` 仅编排调用，与 LangGraph 连接池隔离。

**Tech Stack:** PostgreSQL, SQLAlchemy 2 sync engine, psycopg3, Celery, pytest

**Spec:** `docs/superpowers/specs/2026-05-18-langgraph-checkpoint-retention-design.md`

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| File | Action | Responsibility |
|------|--------|----------------|
| `backend/app/agent/constants.py` | Create | 任务名、advisory lock key |
| `backend/app/config.py` | Modify | 保留天数 / 清理开关 / 批大小 |
| `backend/app/agent/service/checkpoint_purge_service.py` | Create | cutoff 计算、分批 DELETE、advisory lock |
| `backend/app/agent/task/checkpoint_purge_job.py` | Create | `@shared_task` 入口 |
| `backend/app/celery_app.py` | Modify | import 注册任务 |
| `backend/sql/schema_postgresql.sql` | Modify | 三表 CREATE + 触发器 + 索引 |
| `backend/sql/agent_v2_langgraph_migration.sql` | Modify | 存量幂等 ALTER |
| `backend/tests/test_checkpoint_purge.py` | Create | 单元 + 可选集成 |
| `docs/agent-module-design.md` | Modify | §Checkpoint 运维说明 |
| `docs/superpowers/specs/2026-05-18-langgraph-checkpoint-retention-design.md` | Modify | §9 实现对照回填 |

**常量（全计划统一）：**

```python
AGENT_CHECKPOINT_PURGE_TASK_NAME = "agent.checkpoint_purge"
# pg_try_advisory_lock(bigint) — 全站单实例清理
AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY = 2026051801
```

**清理表顺序（固定）：** `checkpoint_writes` → `checkpoint_blobs` → `checkpoints`

---

### Task 1: Settings 三项

**Files:**
- Modify: `backend/app/config.py`（`agent_langgraph_checkpoint_pool_timeout` 字段之后）
- Test: `backend/tests/test_checkpoint_purge.py`（仅 settings 相关用例，Task 2 会扩展）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_checkpoint_purge.py
"""Checkpoint retention purge settings and pure helpers."""

from datetime import datetime, timedelta, timezone

from app.agent.service import checkpoint_purge_service as svc
from app.config import settings


def test_retention_defaults() -> None:
    """Default retention is seven days with cleanup enabled."""
    assert settings.agent_langgraph_checkpoint_retention_days == 7
    assert settings.agent_langgraph_checkpoint_cleanup_enabled is True
    assert settings.agent_langgraph_checkpoint_cleanup_batch_size == 1000


def test_compute_cutoff_uses_utc() -> None:
    """Cutoff is now minus retention days in UTC."""
    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = svc.compute_cutoff(now=now, retention_days=7)
    assert cutoff == datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_checkpoint_purge.py -v`

Expected: `ImportError` 或 `ModuleNotFoundError`（`checkpoint_purge_service` / 新 settings 字段不存在）

- [ ] **Step 3: 在 `Settings` 追加字段**

```python
    agent_langgraph_checkpoint_retention_days: int = Field(
        default=7,
        ge=1,
        le=3650,
        description="LangGraph checkpoint 行保留天数（按 create_at 清理）。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_RETENTION_DAYS",
            "agent_langgraph_checkpoint_retention_days",
        ),
    )
    agent_langgraph_checkpoint_cleanup_enabled: bool = Field(
        default=True,
        description="为 False 时 agent.checkpoint_purge 任务直接跳过。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_CLEANUP_ENABLED",
            "agent_langgraph_checkpoint_cleanup_enabled",
        ),
    )
    agent_langgraph_checkpoint_cleanup_batch_size: int = Field(
        default=1000,
        ge=1,
        le=50_000,
        description="checkpoint 清理每表每轮 DELETE 行数上限。",
        validation_alias=AliasChoices(
            "AGENT_LANGGRAPH_CHECKPOINT_CLEANUP_BATCH_SIZE",
            "agent_langgraph_checkpoint_cleanup_batch_size",
        ),
    )
```

- [ ] **Step 4: 创建最小 `compute_cutoff`（Task 2 会扩展同文件）**

```python
# backend/app/agent/service/checkpoint_purge_service.py
"""LangGraph checkpoint table retention purge (sync SQL)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def compute_cutoff(*, now: datetime, retention_days: int) -> datetime:
    """Return UTC cutoff: rows with ``create_at`` strictly before this are expired."""

    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    else:
        now = now.astimezone(timezone.utc)
    return now - timedelta(days=retention_days)
```

- [ ] **Step 5: 再跑测试**

Run: `cd backend && pytest tests/test_checkpoint_purge.py::test_retention_defaults tests/test_checkpoint_purge.py::test_compute_cutoff_uses_utc -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/config.py backend/app/agent/service/checkpoint_purge_service.py backend/tests/test_checkpoint_purge.py
git commit -m "feat(agent): add checkpoint retention settings and cutoff helper"
```

---

### Task 2: 清理服务（分批 DELETE + advisory lock）

**Files:**
- Create: `backend/app/agent/constants.py`
- Modify: `backend/app/agent/service/checkpoint_purge_service.py`
- Test: `backend/tests/test_checkpoint_purge.py`

- [ ] **Step 1: 写失败测试（mock 连接）**

```python
from unittest.mock import MagicMock, call

from app.agent.constants import AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY
from app.agent.service import checkpoint_purge_service as svc


def test_purge_skipped_when_disabled(monkeypatch) -> None:
    """When cleanup_enabled is false, no SQL runs."""
    monkeypatch.setattr(svc, "_purge_enabled", lambda: False)
    conn = MagicMock()
    result = svc.run_checkpoint_purge(conn)
    assert result == {"skipped": True, "reason": "disabled"}
    conn.execute.assert_not_called()


def test_purge_skipped_when_lock_not_acquired(monkeypatch) -> None:
    """When advisory lock busy, return without deleting."""
    monkeypatch.setattr(svc, "_purge_enabled", lambda: True)
    monkeypatch.setattr(svc, "_try_advisory_lock", lambda _conn: False)
    conn = MagicMock()
    result = svc.run_checkpoint_purge(conn)
    assert result == {"skipped": True, "reason": "lock"}
    conn.execute.assert_not_called()


def test_delete_batch_once() -> None:
    """One batch delete returns cursor rowcount."""
    conn = MagicMock()
    conn.execute.return_value.rowcount = 3
    deleted = svc._delete_expired_batch(
        conn,
        table="checkpoint_writes",
        cutoff=svc.compute_cutoff(
            now=__import__("datetime").datetime(2026, 5, 18, tzinfo=__import__("datetime").timezone.utc),
            retention_days=7,
        ),
        batch_size=1000,
    )
    assert deleted == 3
    sql = str(conn.execute.call_args[0][0])
    assert "checkpoint_writes" in sql
    assert "create_at" in sql


def test_purge_all_tables_loops_until_zero(monkeypatch) -> None:
    """Each table is drained in batches until a batch deletes zero rows."""
    monkeypatch.setattr(svc, "_purge_enabled", lambda: True)
    monkeypatch.setattr(svc, "_try_advisory_lock", lambda _conn: True)
    monkeypatch.setattr(svc, "_release_advisory_lock", lambda _conn: None)
    counts = iter([2, 0, 1, 0, 0, 0])
    monkeypatch.setattr(svc, "_delete_expired_batch", lambda *a, **k: next(counts))
    conn = MagicMock()
    result = svc.run_checkpoint_purge(conn)
    assert result == {"writes": 2, "blobs": 1, "checkpoints": 0, "skipped": False}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && pytest tests/test_checkpoint_purge.py -v -k "purge or delete_batch"`

Expected: FAIL（缺少 constants / 函数）

- [ ] **Step 3: 实现 constants + 完整 purge 服务**

`backend/app/agent/constants.py`:

```python
"""Agent module shared constants."""

from __future__ import annotations

AGENT_CHECKPOINT_PURGE_TASK_NAME = "agent.checkpoint_purge"
AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY = 2026051801

CHECKPOINT_PURGE_TABLES: tuple[str, ...] = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)
```

`checkpoint_purge_service.py` 追加（保持 `compute_cutoff`）：

```python
from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.agent.constants import (
    AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY,
    CHECKPOINT_PURGE_TABLES,
)
from app.config import settings

_DELETE_SQL = """
DELETE FROM {table}
WHERE ctid IN (
  SELECT ctid FROM {table}
  WHERE create_at < :cutoff
  LIMIT :batch
)
"""


def _purge_enabled() -> bool:
    return settings.agent_langgraph_checkpoint_cleanup_enabled


def _try_advisory_lock(conn: Connection) -> bool:
  row = conn.execute(
      text("SELECT pg_try_advisory_lock(:key)"),
      {"key": AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY},
  ).scalar()
  return bool(row)


def _release_advisory_lock(conn: Connection) -> None:
    conn.execute(
        text("SELECT pg_advisory_unlock(:key)"),
        {"key": AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY},
    )


def _delete_expired_batch(
    conn: Connection,
    *,
    table: str,
    cutoff: datetime,
    batch_size: int,
) -> int:
    if table not in CHECKPOINT_PURGE_TABLES:
        raise ValueError(f"unsupported checkpoint table: {table}")
    result = conn.execute(
        text(_DELETE_SQL.format(table=table)),
        {"cutoff": cutoff, "batch": batch_size},
    )
    return int(result.rowcount or 0)


def _purge_table(
    conn: Connection,
    *,
    table: str,
    cutoff: datetime,
    batch_size: int,
) -> int:
    total = 0
    while True:
        n = _delete_expired_batch(
            conn, table=table, cutoff=cutoff, batch_size=batch_size
        )
        total += n
        if n == 0:
            return total


def run_checkpoint_purge(conn: Connection) -> dict[str, object]:
    """Delete expired checkpoint rows; safe to call from Celery."""
    if not _purge_enabled():
        return {"skipped": True, "reason": "disabled"}
    if not _try_advisory_lock(conn):
        return {"skipped": True, "reason": "lock"}
    try:
        cutoff = compute_cutoff(
            now=datetime.now(timezone.utc),
            retention_days=settings.agent_langgraph_checkpoint_retention_days,
        )
        batch = settings.agent_langgraph_checkpoint_cleanup_batch_size
        summary: dict[str, object] = {"skipped": False, "cutoff": cutoff.isoformat()}
        for table in CHECKPOINT_PURGE_TABLES:
            key = table.removeprefix("checkpoint_")  # writes, blobs, checkpoints
            if key == "checkpoints":
                key = "checkpoints"
            elif table == "checkpoint_writes":
                key = "writes"
            elif table == "checkpoint_blobs":
                key = "blobs"
            summary[key] = _purge_table(
                conn, table=table, cutoff=cutoff, batch_size=batch
            )
        return summary
    finally:
        _release_advisory_lock(conn)
```

> **实现时注意：** 上表 `key` 映射在编码时写死为 `writes` / `blobs` / `checkpoints` 三字典键，避免 `removeprefix` 歧义：

```python
_TABLE_RESULT_KEYS = {
    "checkpoint_writes": "writes",
    "checkpoint_blobs": "blobs",
    "checkpoints": "checkpoints",
}
# ...
summary[_TABLE_RESULT_KEYS[table]] = _purge_table(...)
```

- [ ] **Step 4: 运行测试**

Run: `cd backend && pytest tests/test_checkpoint_purge.py -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/constants.py backend/app/agent/service/checkpoint_purge_service.py backend/tests/test_checkpoint_purge.py
git commit -m "feat(agent): add checkpoint purge service with advisory lock"
```

---

### Task 3: Celery 任务注册

**Files:**
- Create: `backend/app/agent/task/checkpoint_purge_job.py`
- Create: `backend/app/agent/task/__init__.py`（若不存在，空文件或 docstring）
- Modify: `backend/app/celery_app.py`

- [ ] **Step 1: 实现任务模块**

```python
# backend/app/agent/task/checkpoint_purge_job.py
"""Celery entry for LangGraph checkpoint retention purge."""

from __future__ import annotations

import logging
from typing import Any

from celery import Task, shared_task
from celery.utils.log import get_task_logger
from sqlalchemy import create_engine

from app.agent.constants import AGENT_CHECKPOINT_PURGE_TASK_NAME
from app.agent.service.checkpoint_purge_service import run_checkpoint_purge
from app.config import settings

logger = get_task_logger(__name__)
log = logging.getLogger(__name__)


def _sync_engine():
    return create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        future=True,
    )


@shared_task(bind=True, name=AGENT_CHECKPOINT_PURGE_TASK_NAME)
def purge_langgraph_checkpoints(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Purge checkpoint tables older than configured retention (ignores beat args)."""
    log.info("agent.checkpoint_purge start task_id=%s", getattr(self.request, "id", None))
    engine = _sync_engine()
    with engine.begin() as conn:
        summary = run_checkpoint_purge(conn)
    log.info("agent.checkpoint_purge done summary=%s", summary)
    return summary
```

- [ ] **Step 2: 在 `celery_app.py` 注册 import**

在现有：

```python
    import app.file_ocr.task.scan_init_job  # noqa: F401
    import app.sys.celery.demo.default_job  # noqa: F401
```

之后追加：

```python
    import app.agent.task.checkpoint_purge_job  # noqa: F401
```

- [ ] **Step 3: 冒烟（无 DB 时跳过）**

Run: `cd backend && python -c "from app.celery_app import celery_app; print([k for k in celery_app.tasks if 'checkpoint' in k])"`

Expected: 输出包含 `agent.checkpoint_purge`

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/task/ backend/app/celery_app.py
git commit -m "feat(agent): register agent.checkpoint_purge celery task"
```

---

### Task 4: `schema_postgresql.sql` 三表 DDL

**Files:**
- Modify: `backend/sql/schema_postgresql.sql`（`agent_run_node` 段之后追加）

- [ ] **Step 1: 追加共享触发器函数 + 三表 CREATE**

在文件末尾 Agent 小节之后插入（**无 FOREIGN KEY**）：

```sql
-- ---------------------------------------------------------------------------
-- LangGraph checkpoint（AsyncPostgresSaver；列定义对齐 langgraph-checkpoint-postgres 3.x）
-- ---------------------------------------------------------------------------

CREATE OR REPLACE FUNCTION public.minerva_checkpoint_set_update_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.update_at := now();
  RETURN NEW;
END;
$$;

CREATE TABLE IF NOT EXISTS public.checkpoints (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  parent_checkpoint_id text NULL,
  type text NULL,
  checkpoint jsonb NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}',
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id)
);
CREATE INDEX IF NOT EXISTS checkpoints_thread_id_idx ON public.checkpoints (thread_id);
CREATE INDEX IF NOT EXISTS ix_checkpoints_create_at ON public.checkpoints (create_at);
DROP TRIGGER IF EXISTS trg_checkpoints_set_update_at ON public.checkpoints;
CREATE TRIGGER trg_checkpoints_set_update_at
  BEFORE UPDATE ON public.checkpoints
  FOR EACH ROW EXECUTE FUNCTION public.minerva_checkpoint_set_update_at();

CREATE TABLE IF NOT EXISTS public.checkpoint_blobs (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  channel text NOT NULL,
  version text NOT NULL,
  type text NOT NULL,
  blob bytea NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, checkpoint_ns, channel, version)
);
CREATE INDEX IF NOT EXISTS checkpoint_blobs_thread_id_idx ON public.checkpoint_blobs (thread_id);
CREATE INDEX IF NOT EXISTS ix_checkpoint_blobs_create_at ON public.checkpoint_blobs (create_at);
DROP TRIGGER IF EXISTS trg_checkpoint_blobs_set_update_at ON public.checkpoint_blobs;
CREATE TRIGGER trg_checkpoint_blobs_set_update_at
  BEFORE UPDATE ON public.checkpoint_blobs
  FOR EACH ROW EXECUTE FUNCTION public.minerva_checkpoint_set_update_at();

CREATE TABLE IF NOT EXISTS public.checkpoint_writes (
  thread_id text NOT NULL,
  checkpoint_ns text NOT NULL DEFAULT '',
  checkpoint_id text NOT NULL,
  task_id text NOT NULL,
  task_path text NOT NULL DEFAULT '',
  idx integer NOT NULL,
  channel text NOT NULL,
  type text NULL,
  blob bytea NOT NULL,
  create_at timestamptz NOT NULL DEFAULT now(),
  update_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (thread_id, checkpoint_ns, checkpoint_id, task_id, idx)
);
CREATE INDEX IF NOT EXISTS checkpoint_writes_thread_id_idx ON public.checkpoint_writes (thread_id);
CREATE INDEX IF NOT EXISTS ix_checkpoint_writes_create_at ON public.checkpoint_writes (create_at);
DROP TRIGGER IF EXISTS trg_checkpoint_writes_set_update_at ON public.checkpoint_writes;
CREATE TRIGGER trg_checkpoint_writes_set_update_at
  BEFORE UPDATE ON public.checkpoint_writes
  FOR EACH ROW EXECUTE FUNCTION public.minerva_checkpoint_set_update_at();

COMMENT ON TABLE public.checkpoints IS 'LangGraph checkpoint 主表';
COMMENT ON COLUMN public.checkpoints.create_at IS '行创建时间（清理依据）';
COMMENT ON COLUMN public.checkpoints.update_at IS '行最后更新时间';
```

（`checkpoint_blobs` / `checkpoint_writes` 同样补 `COMMENT ON COLUMN` 的 `create_at` / `update_at`。）

- [ ] **Step 2: 手工检查**

确认：无 `REFERENCES`；`EXECUTE FUNCTION` 语法与目标 PostgreSQL 版本一致（若环境为 PG14 以下则改为 `EXECUTE PROCEDURE`）。

- [ ] **Step 3: Commit**

```bash
git add backend/sql/schema_postgresql.sql
git commit -m "feat(sql): add LangGraph checkpoint tables with timestamps"
```

---

### Task 5: 存量迁移 `agent_v2_langgraph_migration.sql`

**Files:**
- Modify: `backend/sql/agent_v2_langgraph_migration.sql`

- [ ] **Step 1: 文件末尾追加幂等块**

```sql
-- LangGraph checkpoint: timestamps + indexes + update_at triggers (existing DBs).

CREATE OR REPLACE FUNCTION public.minerva_checkpoint_set_update_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
  NEW.update_at := now();
  RETURN NEW;
END;
$$;

ALTER TABLE public.checkpoints
  ADD COLUMN IF NOT EXISTS create_at timestamptz NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at timestamptz NULL DEFAULT now();
ALTER TABLE public.checkpoint_blobs
  ADD COLUMN IF NOT EXISTS create_at timestamptz NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at timestamptz NULL DEFAULT now();
ALTER TABLE public.checkpoint_writes
  ADD COLUMN IF NOT EXISTS create_at timestamptz NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at timestamptz NULL DEFAULT now();

UPDATE public.checkpoints
SET create_at = COALESCE(create_at, now()), update_at = COALESCE(update_at, now())
WHERE create_at IS NULL OR update_at IS NULL;
UPDATE public.checkpoint_blobs
SET create_at = COALESCE(create_at, now()), update_at = COALESCE(update_at, now())
WHERE create_at IS NULL OR update_at IS NULL;
UPDATE public.checkpoint_writes
SET create_at = COALESCE(create_at, now()), update_at = COALESCE(update_at, now())
WHERE create_at IS NULL OR update_at IS NULL;

ALTER TABLE public.checkpoints
  ALTER COLUMN create_at SET NOT NULL,
  ALTER COLUMN update_at SET NOT NULL;
ALTER TABLE public.checkpoint_blobs
  ALTER COLUMN create_at SET NOT NULL,
  ALTER COLUMN update_at SET NOT NULL;
ALTER TABLE public.checkpoint_writes
  ALTER COLUMN create_at SET NOT NULL,
  ALTER COLUMN update_at SET NOT NULL;

-- task_path（若 LangGraph setup 尚未执行到该 migration）
ALTER TABLE public.checkpoint_writes
  ADD COLUMN IF NOT EXISTS task_path text NOT NULL DEFAULT '';

CREATE INDEX IF NOT EXISTS ix_checkpoints_create_at ON public.checkpoints (create_at);
CREATE INDEX IF NOT EXISTS ix_checkpoint_blobs_create_at ON public.checkpoint_blobs (create_at);
CREATE INDEX IF NOT EXISTS ix_checkpoint_writes_create_at ON public.checkpoint_writes (create_at);

DROP TRIGGER IF EXISTS trg_checkpoints_set_update_at ON public.checkpoints;
CREATE TRIGGER trg_checkpoints_set_update_at
  BEFORE UPDATE ON public.checkpoints
  FOR EACH ROW EXECUTE FUNCTION public.minerva_checkpoint_set_update_at();
DROP TRIGGER IF EXISTS trg_checkpoint_blobs_set_update_at ON public.checkpoint_blobs;
CREATE TRIGGER trg_checkpoint_blobs_set_update_at
  BEFORE UPDATE ON public.checkpoint_blobs
  FOR EACH ROW EXECUTE FUNCTION public.minerva_checkpoint_set_update_at();
DROP TRIGGER IF EXISTS trg_checkpoint_writes_set_update_at ON public.checkpoint_writes;
CREATE TRIGGER trg_checkpoint_writes_set_update_at
  BEFORE UPDATE ON public.checkpoint_writes
  FOR EACH ROW EXECUTE FUNCTION public.minerva_checkpoint_set_update_at();
```

> 若目标库 **尚无** 三表，本段 `ALTER` 会失败——文档注明：须先启动一次 Agent（`setup()`）或先跑 `schema_postgresql.sql` checkpoint 段。

- [ ] **Step 2: Commit**

```bash
git add backend/sql/agent_v2_langgraph_migration.sql
git commit -m "feat(sql): migrate existing checkpoint tables with timestamps"
```

---

### Task 6: 集成测试（可选，有 DB 时）

**Files:**
- Modify: `backend/tests/test_checkpoint_purge.py`

- [ ] **Step 1: 添加 DB 集成测试**

```python
import os
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text

from app.agent.service import checkpoint_purge_service as svc
from app.config import settings

pytestmark = pytest.mark.skipif(
    os.getenv("MINERVA_SKIP_DB_TESTS", "").lower() in ("1", "true", "yes"),
    reason="MINERVA_SKIP_DB_TESTS set",
)


@pytest.fixture
def sync_conn():
    engine = create_engine(settings.sync_database_url, future=True)
    with engine.begin() as conn:
        # 确保列存在（测试库可能未跑迁移）
        conn.execute(text("SELECT 1 FROM checkpoints LIMIT 1"))
        yield conn
        raise AssertionError("use nested transaction in real impl")


def test_integration_purge_deletes_old_row(sync_conn):
    """Row with create_at 30 days ago is removed."""
    ...
```

> 实现时：用 `thread_id = 'test-purge-' || uuid` 插入 `checkpoints` 一行，`create_at` 设为 `now()-30d`，调用 `run_checkpoint_purge`，断言该行不存在。测试结束 `DELETE` 清理。

- [ ] **Step 2: 运行**

Run: `cd backend && pytest tests/test_checkpoint_purge.py -v -m "not skip"`  
（或显式 unset `MINERVA_SKIP_DB_TESTS`）

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_checkpoint_purge.py
git commit -m "test(agent): integration test for checkpoint purge"
```

---

### Task 7: 文档回填

**Files:**
- Modify: `docs/agent-module-design.md`
- Modify: `docs/superpowers/specs/2026-05-18-langgraph-checkpoint-retention-design.md`

- [ ] **Step 1: `agent-module-design.md` §15 第 4 点扩展为：**

- 三表 `create_at` / `update_at` 与触发器说明
- Settings：`agent_langgraph_checkpoint_retention_days` 等三项
- `sys_celery`：`task=agent.checkpoint_purge`，`task_code=agent_checkpoint_purge`，建议 cron `0 0 3 * * *`，全站仅一条启用
- 存量执行：`psql -f backend/sql/agent_v2_langgraph_migration.sql`

- [ ] **Step 2: spec §9 实现对照表填入实际路径与 lock key `2026051801`；状态改为「已实现」**

- [ ] **Step 3: Commit**

```bash
git add docs/agent-module-design.md docs/superpowers/specs/2026-05-18-langgraph-checkpoint-retention-design.md
git commit -m "docs: document checkpoint retention and purge task"
```

---

### Task 8: 运维验证清单（手工）

- [ ] **Step 1: 存量库执行迁移**

```bash
psql -U minerva -d minerva -f backend/sql/agent_v2_langgraph_migration.sql
```

- [ ] **Step 2: 在某一 workspace 的 `sys_celery` 新增任务**

| 字段 | 值 |
|------|-----|
| `task_code` | `agent_checkpoint_purge` |
| `task` | `agent.checkpoint_purge` |
| `cron` | `0 0 3 * * *` |
| `enabled` | `true` |

- [ ] **Step 3: 启动 Worker + Beat，观察日志 `agent.checkpoint_purge done summary=...`**

- [ ] **Step 4: 确认 LangGraph Agent run 仍可正常 checkpoint（`agent_langgraph_checkpoint_enabled=true`）**

---

## Plan self-review（已完成）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| schema 三表 + 时间列 + 索引 + 触发器 | Task 4 |
| 存量 agent_v2 迁移 | Task 5 |
| Settings 默认 7 天 | Task 1 |
| Celery + sys_celery 调度 | Task 3 + Task 8 |
| 仅 create_at 清理 | Task 2 |
| update_at 触发器 | Task 4、5 |
| advisory lock | Task 2 |
| 文档 | Task 7 |
| 测试 | Task 1–2、6 |

无 TBD；advisory lock key 固定为 `2026051801`。

---

## 执行方式

Plan 已保存至 `docs/superpowers/plans/2026-05-18-langgraph-checkpoint-retention.md`。

可选执行方式：

1. **Subagent-Driven（推荐）** — 每个 Task 派发子 agent，任务间做审查  
2. **Inline Execution** — 本会话按 Task 顺序实现，关键节点停顿确认  

你希望用哪种方式开始实现？
