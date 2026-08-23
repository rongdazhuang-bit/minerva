# 知识图谱 GraphKB（GraphRAG / LightRAG）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 落地独立「知识图谱」模块：工作区共享图谱 + 用户 ACL，建库时二选一 GraphRAG 或 LightRAG，菜单内完成建图、表格/画布/摘要浏览与问答；主 API 不 import 引擎 SDK。

**Architecture:** Minerva `app/graph_kb` 拥有元数据、ACL、文档、任务与只读投影；Celery `graph_kb` 队列编排；独立 LightRAG / GraphRAG Worker 按 `(workspace_id, graph_id)` 拼接 namespace。Dataset 与 mem0 Neo4j 不改。

**Tech Stack:** FastAPI, SQLAlchemy 2.x, Pydantic v2, Celery, httpx, pytest, React 18, Ant Design, `@antv/g6`（画布），LightRAG / microsoft-graphrag 仅装在各自 Worker venv。

**设计依据:** `docs/superpowers/specs/2026-08-23-graph-kb-graphrag-lightrag-design.md`

## Global Constraints

- 无库级外键 / `ON DELETE CASCADE`；删除在 service 层按 spec §5.7 顺序执行。
- 主 API 与主 Celery 进程禁止 `import lightrag` / `import graphrag`。
- Worker 只接收 `workspace_id` + `graph_id`，自行拼接 namespace；拒绝调用方传入的自由 workspace 字符串。
- 超管绕过 feature / 成员 / 图谱 ACL；workspace admin 可见并管理本空间全部图谱。
- 未授权单库访问返回 **404**（超管除外）。
- 日志用 `from app.core.log import get_logger` + `{}` 占位；禁止明文 api_key。
- 类与方法必须有 docstring（code-comments skill）。
- 分页默认 10：`app.pagination.DEFAULT_PAGE_SIZE` / `frontend/src/constants/pagination.ts`。
- 前端删除用 `Popconfirm`；主内容区 4px 圆角、外框、页内滚动。
- 环境变量变更必须同步 `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev`。
- LightRAG 不得使用 `MEM0_*` / `MEM0_NEO4J_*`。

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/app/config.py` | `GRAPH_KB_*` Settings |
| `backend/.env.example`, `backend/.env.dev` | 同步环境变量 |
| `backend/app/core/security/permission_codes.py` | `FEATURE_GRAPH_KB` |
| `backend/sql/schema_postgresql.sql` | `graph_kb*` 表 |
| `backend/sql/patches/2026-08-23-graph-kb-tables.sql` | 已有库 DDL |
| `backend/sql/patches/2026-08-23-graph-kb-feature-menu.sql` | 权限码 + 菜单 |
| `backend/sql/seeds/sys_menu_seed.sql` | 新菜单行 |
| `backend/scripts/gen_sys_menu_seed_uuids.py` | 菜单种子行 |
| `backend/app/graph_kb/**` | 领域、ACL、仓储、服务、API、Celery |
| `backend/app/core/api/router.py` | 挂载 router |
| `scripts/run-celery.cmd`, `scripts/run-celery.sh` | 默认队列加 `graph_kb` |
| `workers/graph-kb-lightrag/**` | 独立 LightRAG Worker |
| `workers/graph-kb-graphrag/**` | 独立 GraphRAG Worker |
| `scripts/run-graph-kb-lightrag-worker.cmd` | 启动 LightRAG Worker |
| `scripts/run-graph-kb-graphrag-worker.cmd` | 启动 GraphRAG Worker |
| `frontend/src/features/graph-kb/**` | 页面与 API |
| `frontend/src/app/router.tsx` | 路由 |
| `frontend/src/i18n/locales/zh-CN.json`, `en.json` | i18n |
| `docs/superpowers/specs/2026-08-23-graph-kb-graphrag-lightrag-design.md` | 实现对照回填 |

---

### Task 1: 权限码、配置、namespace 纯函数

**Files:**
- Modify: `backend/app/core/security/permission_codes.py`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`
- Create: `backend/app/graph_kb/__init__.py`
- Create: `backend/app/graph_kb/domain/__init__.py`
- Create: `backend/app/graph_kb/domain/constants.py`
- Create: `backend/app/graph_kb/domain/namespace.py`
- Test: `backend/tests/test_graph_kb_namespace.py`

**Interfaces:**
- Consumes: 无
- Produces: `FEATURE_GRAPH_KB = "feature:graph_kb"`；`lightrag_workspace(workspace_id, graph_id) -> str`；`graphrag_root(data_root, workspace_id, graph_id) -> Path`；Settings 字段见 Step 3

- [ ] **Step 1: Write the failing test**

```python
"""Namespace helpers for GraphKB engine isolation."""

from pathlib import Path
from uuid import UUID

from app.graph_kb.domain.namespace import graphrag_root, lightrag_workspace


def test_lightrag_workspace_uses_hex_ids() -> None:
    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    assert lightrag_workspace(wid, gid) == (
        "kg_11111111111111111111111111111111_22222222222222222222222222222222"
    )


def test_graphrag_root_nests_workspace_then_graph(tmp_path: Path) -> None:
    wid = UUID("11111111-1111-1111-1111-111111111111")
    gid = UUID("22222222-2222-2222-2222-222222222222")
    root = graphrag_root(tmp_path, wid, gid)
    assert root == tmp_path / str(wid) / str(gid)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_graph_kb_namespace.py -v
```

Expected: FAIL（`app.graph_kb` 不存在）。

- [ ] **Step 3: Write minimal implementation**

`permission_codes.py`：增加 `FEATURE_GRAPH_KB = "feature:graph_kb"`，加入 `FEATURE_CODES`，并在 `menu_key_to_feature` 中：

```python
    if menu_key == "sub-graph-kb" or fnmatch.fnmatch(menu_key, "graph-kb-*"):
        return FEATURE_GRAPH_KB
```

`domain/constants.py`：

```python
"""GraphKB enums and Celery task names."""

ENGINE_GRAPHRAG = "graphrag"
ENGINE_LIGHTRAG = "lightrag"
ENGINES = frozenset({ENGINE_GRAPHRAG, ENGINE_LIGHTRAG})

PERMISSION_ONLY_ME = "only_me"
PERMISSION_PARTIAL_MEMBERS = "partial_members"
PERMISSION_ALL_TEAM_MEMBERS = "all_team_members"
PERMISSIONS = frozenset(
    {PERMISSION_ONLY_ME, PERMISSION_PARTIAL_MEMBERS, PERMISSION_ALL_TEAM_MEMBERS}
)

QUERY_LOCAL = "local"
QUERY_GLOBAL = "global"
QUERY_HYBRID = "hybrid"
QUERY_NAIVE = "naive"
QUERY_MODES = frozenset({QUERY_LOCAL, QUERY_GLOBAL, QUERY_HYBRID, QUERY_NAIVE})

SOURCE_UPLOAD_FILE = "upload_file"
SOURCE_PLAIN_TEXT = "plain_text"

STATUS_EMPTY = "empty"
STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"

JOB_INDEX = "index"
JOB_REINDEX = "reindex"
JOB_CLEANUP = "cleanup"

GRAPH_KB_INDEX_TASK_NAME = "graph_kb.index"
GRAPH_KB_CLEANUP_TASK_NAME = "graph_kb.cleanup"

ALLOWED_UPLOAD_SUFFIXES = frozenset({".txt", ".md", ".pdf", ".docx", ".html", ".csv"})
```

`domain/namespace.py`：

```python
"""Build engine namespaces from workspace_id + graph_id only."""

from pathlib import Path
from uuid import UUID


def lightrag_workspace(workspace_id: UUID, graph_id: UUID) -> str:
    """Return LightRAG workspace key ``kg_{wid_hex}_{gid_hex}``."""

    return f"kg_{workspace_id.hex}_{graph_id.hex}"


def graphrag_root(data_root: Path, workspace_id: UUID, graph_id: UUID) -> Path:
    """Return GraphRAG silo directory ``{data_root}/{workspace_id}/{graph_id}``."""

    return Path(data_root) / str(workspace_id) / str(graph_id)
```

`config.py` 在 dataset 配置块后增加（`AliasChoices` 与现网一致）：

| 字段 | 默认 | alias |
|------|------|-------|
| `graph_kb_data` | `""`（空则 `{repo}/data/graph_kb`，实现里用 `Path` 解析） | `GRAPH_KB_DATA` |
| `graph_kb_lightrag_database_url` | `""` | `GRAPH_KB_LIGHTRAG_DATABASE_URL` |
| `graph_kb_job_timeout_seconds` | `7200` | `GRAPH_KB_JOB_TIMEOUT_SECONDS` |
| `graph_kb_inline_text_max_chars` | `20000` | `GRAPH_KB_INLINE_TEXT_MAX_CHARS` |
| `graph_kb_lightrag_worker_url` | `http://127.0.0.1:8101` | `GRAPH_KB_LIGHTRAG_WORKER_URL` |
| `graph_kb_graphrag_worker_url` | `http://127.0.0.1:8102` | `GRAPH_KB_GRAPHRAG_WORKER_URL` |

增加方法：

```python
    def resolve_graph_kb_data(self) -> Path:
        """Return GraphRAG data root; default ``<cwd>/data/graph_kb`` when unset."""

        raw = (self.graph_kb_data or "").strip()
        return Path(raw) if raw else Path.cwd() / "data" / "graph_kb"
```

`.env.example` / `.env.dev` 增加同名键与中文注释；注释写明禁止复用 `MEM0_*`。

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_graph_kb_namespace.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/security/permission_codes.py backend/app/config.py backend/.env.example backend/.env.dev backend/app/graph_kb backend/tests/test_graph_kb_namespace.py
git commit -m "feat(graph-kb): add feature code, settings, and engine namespaces"
```

---

### Task 2: ACL 纯函数

**Files:**
- Create: `backend/app/graph_kb/domain/acl.py`
- Test: `backend/tests/test_graph_kb_acl.py`

**Interfaces:**
- Consumes: `PERMISSION_*` constants；`MembershipRole`
- Produces: `GraphAclActor`；`GraphAclSubject`；`can_view_graph(...)`；`can_manage_graph(...)`；`raise_if_cannot_view(...)`（否 → `AppError(..., 404)`）

- [ ] **Step 1: Write the failing test**

```python
"""GraphKB ACL: super-admin, workspace admin, and member permissions."""

from uuid import uuid4

import pytest

from app.core.domain.identity.models import MembershipRole
from app.exceptions import AppError
from app.graph_kb.domain.acl import (
    GraphAclActor,
    GraphAclSubject,
    can_manage_graph,
    can_view_graph,
    raise_if_cannot_view,
)
from app.graph_kb.domain.constants import (
    PERMISSION_ALL_TEAM_MEMBERS,
    PERMISSION_ONLY_ME,
    PERMISSION_PARTIAL_MEMBERS,
)


def _subject(permission: str, created_by):
    return GraphAclSubject(
        graph_id=uuid4(),
        workspace_id=uuid4(),
        permission=permission,
        created_by=created_by,
    )


def test_super_admin_views_only_me_graph() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=True, workspace_role=None
    )
    assert can_view_graph(actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner), member_ids=set())


def test_workspace_admin_views_only_me_of_other_user() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.admin
    )
    assert can_view_graph(actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner), member_ids=set())


def test_member_cannot_view_others_only_me() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert not can_view_graph(
        actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner), member_ids=set()
    )


def test_member_views_all_team_members() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert can_view_graph(
        actor=actor,
        graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()),
        member_ids=set(),
    )


def test_partial_member_can_view() -> None:
    user = uuid4()
    actor = GraphAclActor(
        user_id=user, is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert can_view_graph(
        actor=actor,
        graph=_subject(PERMISSION_PARTIAL_MEMBERS, uuid4()),
        member_ids={user},
    )


def test_non_member_cannot_view() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=None
    )
    assert not can_view_graph(
        actor=actor,
        graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()),
        member_ids=set(),
    )


def test_creator_can_manage_own_graph() -> None:
    owner = uuid4()
    actor = GraphAclActor(
        user_id=owner, is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert can_manage_graph(actor=actor, graph=_subject(PERMISSION_ONLY_ME, owner))


def test_member_cannot_manage_others_graph() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    assert not can_manage_graph(actor=actor, graph=_subject(PERMISSION_ALL_TEAM_MEMBERS, uuid4()))


def test_raise_if_cannot_view_is_404() -> None:
    actor = GraphAclActor(
        user_id=uuid4(), is_super_admin=False, workspace_role=MembershipRole.member
    )
    with pytest.raises(AppError) as exc:
        raise_if_cannot_view(
            actor=actor,
            graph=_subject(PERMISSION_ONLY_ME, uuid4()),
            member_ids=set(),
        )
    assert exc.value.status_code == 404
    assert exc.value.code == "graph_kb.not_found"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_graph_kb_acl.py -v
```

Expected: FAIL（`acl` 模块不存在）。

- [ ] **Step 3: Write minimal implementation**

```python
"""Workspace-shared graph ACL: super-admin, admin overview, member visibility."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.core.domain.identity.models import MembershipRole
from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    PERMISSION_ALL_TEAM_MEMBERS,
    PERMISSION_ONLY_ME,
    PERMISSION_PARTIAL_MEMBERS,
)


@dataclass(frozen=True)
class GraphAclActor:
    """Caller identity for a GraphKB authorization decision."""

    user_id: UUID
    is_super_admin: bool
    workspace_role: MembershipRole | None


@dataclass(frozen=True)
class GraphAclSubject:
    """Graph fields required to evaluate ACL."""

    graph_id: UUID
    workspace_id: UUID
    permission: str
    created_by: UUID


def can_view_graph(
    *,
    actor: GraphAclActor,
    graph: GraphAclSubject,
    member_ids: set[UUID],
) -> bool:
    """Return whether actor may read the graph (list, browse, query)."""

    if actor.is_super_admin:
        return True
    if actor.workspace_role is None:
        return False
    if actor.workspace_role == MembershipRole.admin:
        return True
    if graph.created_by == actor.user_id:
        return True
    if graph.permission == PERMISSION_ALL_TEAM_MEMBERS:
        return True
    if graph.permission == PERMISSION_PARTIAL_MEMBERS and actor.user_id in member_ids:
        return True
    if graph.permission == PERMISSION_ONLY_ME:
        return False
    return False


def can_manage_graph(*, actor: GraphAclActor, graph: GraphAclSubject) -> bool:
    """Return whether actor may change ACL, delete, or reindex the graph."""

    if actor.is_super_admin:
        return True
    if actor.workspace_role == MembershipRole.admin:
        return True
    return graph.created_by == actor.user_id


def raise_if_cannot_view(
    *,
    actor: GraphAclActor,
    graph: GraphAclSubject,
    member_ids: set[UUID],
) -> None:
    """Raise 404 when the caller cannot view the graph."""

    if not can_view_graph(actor=actor, graph=graph, member_ids=member_ids):
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)


def raise_if_cannot_manage(*, actor: GraphAclActor, graph: GraphAclSubject) -> None:
    """Raise 404 when the caller cannot manage the graph."""

    if not can_manage_graph(actor=actor, graph=graph):
        raise AppError("graph_kb.not_found", "知识图谱不存在。", 404)
```

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_graph_kb_acl.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/domain/acl.py backend/tests/test_graph_kb_acl.py
git commit -m "feat(graph-kb): add workspace and user ACL helpers"
```

---

### Task 3: ORM 与 DDL

**Files:**
- Create: `backend/app/graph_kb/domain/db/__init__.py`
- Create: `backend/app/graph_kb/domain/db/models.py`
- Modify: `backend/sql/schema_postgresql.sql`
- Create: `backend/sql/patches/2026-08-23-graph-kb-tables.sql`
- Test: `backend/tests/test_graph_kb_models.py`

**Interfaces:**
- Consumes: 无 FK；表名与 spec §5 一致
- Produces: `GraphKb`, `GraphKbMember`, `GraphKbDocument`, `GraphKbJob`, `GraphKbQuery`, `GraphKbEntity`, `GraphKbRelation`, `GraphKbCommunity`

- [ ] **Step 1: Write the failing test**

```python
"""GraphKB ORM table names and required columns."""

from app.graph_kb.domain.db.models import GraphKb, GraphKbMember


def test_graph_kb_table_and_columns() -> None:
    assert GraphKb.__tablename__ == "graph_kb"
    cols = {c.key for c in GraphKb.__table__.columns}
    assert {"workspace_id", "engine", "permission", "created_by"} <= cols


def test_member_unique_constraint_name() -> None:
    names = {c.name for c in GraphKbMember.__table__.constraints}
    assert "uq_graph_kb_member_graph_user" in names
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_graph_kb_models.py -v
```

Expected: FAIL。

- [ ] **Step 3: Write models and SQL**

`models.py` 对齐 Dataset 风格：`UUID(as_uuid=True)`、`create_at` / `update_at`、`server_default=text("now()")`。`GraphKbMember` 增加：

```python
    __table_args__ = (
        UniqueConstraint("graph_id", "user_id", name="uq_graph_kb_member_graph_user"),
    )
```

列与 spec §5 一致。类 docstring 须写明逻辑引用哪张表（无 FK）。

`schema_postgresql.sql` 与 patch 使用相同 DDL。每张表：`id UUID PK DEFAULT gen_random_uuid()`；`workspace_id` / `graph_id` 建索引；**不要** `REFERENCES`。文件头注释写「无外键」。

对 `graph_kb_query.citations` 使用 `jsonb NULL`。

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_graph_kb_models.py -v
```

Expected: PASS。本地已有库时执行 patch：

```bash
psql %DATABASE_URL% -f backend/sql/patches/2026-08-23-graph-kb-tables.sql
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/domain/db backend/sql/schema_postgresql.sql backend/sql/patches/2026-08-23-graph-kb-tables.sql backend/tests/test_graph_kb_models.py
git commit -m "feat(graph-kb): add graph_kb tables and ORM models"
```

---

### Task 4: Repository 与图谱 CRUD / 列表过滤

**Files:**
- Create: `backend/app/graph_kb/infrastructure/__init__.py`
- Create: `backend/app/graph_kb/infrastructure/repository.py`
- Create: `backend/app/graph_kb/service/__init__.py`
- Create: `backend/app/graph_kb/service/actor.py`
- Create: `backend/app/graph_kb/service/graph_service.py`
- Test: `backend/tests/test_graph_kb_list_filter.py`

**Interfaces:**
- Consumes: `GraphAclActor` / `can_view_graph` / `can_manage_graph`
- Produces:
  - `async def actor_from_user(session, *, user: User, workspace_id: UUID) -> GraphAclActor`
  - `async def create_graph(session, *, workspace_id, user_id, name, engine, permission, llm_*, embedding_*) -> GraphKb`
  - `async def list_graphs_for_actor(session, *, workspace_id, actor, page, page_size, name=None, mine_only=False) -> tuple[list[GraphKb], int]`
  - `async def get_graph_for_view/manage(...) -> GraphKb`
  - `async def patch_graph(...)`（不可改 `engine`）
  - `async def replace_members(session, *, graph_id, workspace_id, user_ids, created_by)`

`actor_from_user`：`user.is_super_admin` + `find_workspace_role_for_user(session, user_id, workspace_id)`。

列表：先查 `workspace_id` 下全部（可按 name ILIKE），再在 Python 中用 ACL 过滤后切片。`mine_only=True` 时再限制 `created_by == actor.user_id`。admin/超管不过滤 ACL；成员过滤。实现时若数据量大可改为 SQL OR，首期内存过滤可接受（单测覆盖过滤正确性）。

- [ ] **Step 1: Write the failing test**

```python
"""In-memory list filter matches ACL (no DB)."""

from uuid import uuid4

from app.core.domain.identity.models import MembershipRole
from app.graph_kb.domain.acl import GraphAclActor, GraphAclSubject, can_view_graph
from app.graph_kb.domain.constants import PERMISSION_ALL_TEAM_MEMBERS, PERMISSION_ONLY_ME
from app.graph_kb.service.graph_service import filter_graphs_for_actor


class _Row:
    def __init__(self, permission: str, created_by):
        self.id = uuid4()
        self.workspace_id = uuid4()
        self.permission = permission
        self.created_by = created_by


def test_filter_hides_only_me_from_other_member() -> None:
    owner = uuid4()
    other = uuid4()
    rows = [_Row(PERMISSION_ONLY_ME, owner), _Row(PERMISSION_ALL_TEAM_MEMBERS, owner)]
    actor = GraphAclActor(
        user_id=other, is_super_admin=False, workspace_role=MembershipRole.member
    )
    visible = filter_graphs_for_actor(rows, actor=actor, members_by_graph={})
    assert [r.permission for r in visible] == [PERMISSION_ALL_TEAM_MEMBERS]
```

把 `filter_graphs_for_actor` 做成纯函数，便于单测：对每个 row 构造 `GraphAclSubject`，`member_ids = members_by_graph.get(row.id, set())`。

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && pytest tests/test_graph_kb_list_filter.py -v
```

Expected: FAIL。

- [ ] **Step 3: Implement repository + service**

`repository.py`：`insert` / `get_by_id` / `list_by_workspace` / `list_member_user_ids` / `replace_members` / `update_fields`。查询必须带 `workspace_id`。

`graph_service.create_graph`：校验 `engine in ENGINES`、`permission in PERMISSIONS`；`indexing_status=empty`。引擎一旦写入不可在 patch 中出现；若 body 带不同 `engine` → `AppError("graph_kb.engine_immutable", "...", 400)`。

- [ ] **Step 4: Run tests**

```bash
cd backend && pytest tests/test_graph_kb_list_filter.py tests/test_graph_kb_acl.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/infrastructure backend/app/graph_kb/service backend/tests/test_graph_kb_list_filter.py
git commit -m "feat(graph-kb): add graph repository and ACL list filter"
```

---

### Task 5: HTTP API（图谱 CRUD）

**Files:**
- Create: `backend/app/graph_kb/api/__init__.py`
- Create: `backend/app/graph_kb/api/deps.py`
- Create: `backend/app/graph_kb/api/schemas.py`
- Create: `backend/app/graph_kb/api/router.py`
- Modify: `backend/app/core/api/router.py`
- Test: `backend/tests/test_graph_kb_api.py`（可用现有 auth fixture；若无则测 service + 路由注册）

**Interfaces:**
- Consumes: `make_require_feature_workspace(FEATURE_GRAPH_KB)` 命名为 `require_graph_kb_workspace`
- Produces: 前缀 `/workspaces/{workspace_id}/graph-kbs`

`deps.py`：

```python
from app.core.security.permission_codes import FEATURE_GRAPH_KB
from app.core.security.permission_deps import make_require_feature_workspace

require_graph_kb_workspace = make_require_feature_workspace(FEATURE_GRAPH_KB)
```

路由（本 Task 只做图谱资源）：

| 方法 | 路径 |
|------|------|
| GET | `` |
| POST | `` |
| GET | `/{graph_id}` |
| PATCH | `/{graph_id}` |
| DELETE | `/{graph_id}`（本 Task 先同步删业务行；异步 cleanup 在 Task 8 接入，可先留 `enqueue_cleanup` no-op 接口） |

Schemas：`GraphKbCreateIn`（name, description, engine, permission, llm_model, llm_model_provider, embedding_model, embedding_model_provider, member_user_ids: list[UUID] = []）；`GraphKbPatchIn`（无 engine）；`GraphKbOut`；`GraphKbListPageOut`（items, total, page, page_size）。

DELETE 本 Task 实现 `deletion_service.delete_graph_sql`（spec 顺序，不含对象存储与 Worker）。测试用 sqlite/postgres 视仓库现有 dataset 测试方式：若 `tests/` 已有 async session fixture，复用；否则对本 Task 用 `TestClient` + mock service。

优先写：

```python
def test_router_prefix() -> None:
    from app.graph_kb.api.router import router

    assert router.prefix == "/workspaces/{workspace_id}/graph-kbs"
```

并在 `app.core.api.router` `include_router(graph_kbs_router)`。

创建时若 `permission=partial_members` 且 `member_user_ids` 为空，允许（仅创建者可见）。

- [ ] **Step 1–4:** 先写 `test_router_prefix` 失败 → 实现 router 与挂载 → PASS
- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/api backend/app/core/api/router.py backend/tests/test_graph_kb_api.py backend/app/graph_kb/service/deletion_service.py
git commit -m "feat(graph-kb): add workspace graph-kbs REST CRUD"
```

`deletion_service.delete_graph_sql(session, *, workspace_id, graph_id)` 按 spec §5.7 同步删除。本 Task DELETE 调用它。

---

### Task 6: 文档上传与纯文本 + 模型校验

**Files:**
- Create: `backend/app/graph_kb/service/model_resolver.py`
- Create: `backend/app/graph_kb/service/document_service.py`
- Modify: `backend/app/graph_kb/api/router.py`
- Modify: `backend/app/graph_kb/api/schemas.py`
- Test: `backend/tests/test_graph_kb_documents.py`

**Interfaces:**
- Consumes: `resolve_model` + `MODEL_TAG_CHAT` / `MODEL_TAG_EMBEDDINGS`（抄 `dataset/service/embedding_resolver.py` 模式）
- Produces:
  - `async def resolve_graph_models(session, *, workspace_id, llm_provider, llm_name, emb_provider, emb_name) -> tuple[ResolvedModel, ResolvedModel]`
  - `async def add_plain_text(...)`
  - `async def add_upload_file(...)`
  - 纯文本长度 `<= settings.graph_kb_inline_text_max_chars` 写入 `text_content`；超过则写入 `{resolve_graph_kb_data()}/{workspace_id}/{graph_id}/texts/{document_id}.txt`，`text_content` 只留前 500 字预览，`storage_key` 为该相对路径

`resolve_graph_models`：Chat 无则 `AppError("graph_kb.llm_model_not_found", "...", 400)`；Embedding 无则 `graph_kb.embedding_model_not_found`。创建图谱与入队 index 都调用。

上传后缀不在 `ALLOWED_UPLOAD_SUFFIXES` → 400 `graph_kb.file_type_unsupported`。

路由：

- `POST /{graph_id}/documents/upload`
- `POST /{graph_id}/documents/text` body: `{ "name": str, "text": str }`
- `GET /{graph_id}/documents`
- `DELETE /{graph_id}/documents/{doc_id}`：删行；若 `indexing_status in {completed, failed}` 则尝试 `enqueue_index`；已有 running job → 文档已删，返回 200 且 `reindex_enqueued: false`（与 spec 409 等价信息：响应字段明确，避免客户端丢文档）。spec 写 409 的是「自动入队失败」；实现为 200 + `reindex_enqueued`，并在 body 说明需手动 `POST /index`。

- [ ] **Step 1:** 单测 `add_plain_text` 拒绝空文本；`resolve` 在无模型时抛 400（mock session 或抽 `_validate_suffix(name)` 纯函数）。

```python
from app.graph_kb.service.document_service import validate_upload_filename
from app.exceptions import AppError


def test_reject_exe() -> None:
    try:
        validate_upload_filename("x.exe")
    except AppError as exc:
        assert exc.status_code == 400
        assert exc.code == "graph_kb.file_type_unsupported"
    else:
        raise AssertionError("expected AppError")


def test_allow_md() -> None:
    validate_upload_filename("note.md")
```

- [ ] **Step 2–4:** 失败 → 实现 → PASS
- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/service/model_resolver.py backend/app/graph_kb/service/document_service.py backend/app/graph_kb/api backend/tests/test_graph_kb_documents.py
git commit -m "feat(graph-kb): add document upload, text import, and model checks"
```

---

### Task 7: Worker 协议、Fake 客户端、HTTP 客户端

**Files:**
- Create: `backend/app/graph_kb/engine/__init__.py`
- Create: `backend/app/graph_kb/engine/types.py`
- Create: `backend/app/graph_kb/engine/protocol.py`
- Create: `backend/app/graph_kb/engine/fake_client.py`
- Create: `backend/app/graph_kb/engine/http_client.py`
- Create: `backend/app/graph_kb/engine/factory.py`
- Create: `backend/app/graph_kb/engine/modes.py`
- Test: `backend/tests/test_graph_kb_engine_client.py`

**Interfaces:**
- Consumes: `lightrag_workspace` / `graphrag_root` 仅在 Worker 侧使用；**主 API 的 HTTP 客户端不得把拼好的 workspace 字符串发给 Worker**
- Produces:

```python
@dataclass(frozen=True)
class ModelEndpoint:
    base_url: str
    api_key: str
    model: str

@dataclass(frozen=True)
class WorkerDocument:
    document_id: UUID
    name: str
    text: str

@dataclass(frozen=True)
class WorkerIndexRequest:
    workspace_id: UUID
    graph_id: UUID
    engine: str
    documents: list[WorkerDocument]
    llm: ModelEndpoint
    embedding: ModelEndpoint

@dataclass(frozen=True)
class GraphExport:
    entities: list[dict]
    relations: list[dict]

@dataclass(frozen=True)
class SummaryItem:
    summary_id: str
    title: str
    content: str
    level: int
    parent_id: str | None

@dataclass(frozen=True)
class WorkerQueryRequest:
    workspace_id: UUID
    graph_id: UUID
    engine: str
    query: str
    mode: str
    top_k: int

@dataclass(frozen=True)
class WorkerQueryResult:
    answer: str
    citations: list[dict]

class GraphEngineClient(Protocol):
    async def index(self, req: WorkerIndexRequest) -> GraphExport: ...
    async def query(self, req: WorkerQueryRequest) -> WorkerQueryResult: ...
    async def export_graph(self, *, engine: str, workspace_id: UUID, graph_id: UUID) -> GraphExport: ...
    async def list_summaries(self, *, engine: str, workspace_id: UUID, graph_id: UUID) -> list[SummaryItem]: ...
    async def delete_namespace(self, *, engine: str, workspace_id: UUID, graph_id: UUID) -> None: ...
```

`modes.py`：

```python
def map_query_mode(engine: str, mode: str) -> str:
    """Validate unified mode; GraphRAG+naive raises AppError 400."""

    if mode not in QUERY_MODES:
        raise AppError("graph_kb.invalid_mode", "不支持的检索模式。", 400)
    if engine == ENGINE_GRAPHRAG and mode == QUERY_NAIVE:
        raise AppError("graph_kb.invalid_mode", "GraphRAG 不支持 naive 模式。", 400)
    return mode
```

`FakeGraphEngineClient`：按 `(workspace_id, graph_id)` 存在进程内 dict；`index` 把文档拼成一个实体 + 一条关系 + 一条 summary，供后续任务测投影。`query` 返回 `"fake:" + query`。

`HttpGraphEngineClient`：按 `engine` 选 `settings.graph_kb_lightrag_worker_url` 或 `graph_kb_graphrag_worker_url`；`httpx.AsyncClient.post(f"{base}/{action}", json=payload, timeout=settings.graph_kb_job_timeout_seconds)`。JSON 字段：`workspace_id`、`graph_id`（字符串 UUID），**没有** `lightrag_workspace` 键。失败：连接错误 → `AppError("graph_kb.worker_unavailable", "...", 503)`。

`factory.create_engine_client() -> GraphEngineClient`：若 `GRAPH_KB_ENGINE_CLIENT=fake`（新增 Settings，默认 `http`；测试设 `fake`）返回 Fake。同步 `.env.example` / `.env.dev`。

- [ ] **Step 1: 失败测试**

```python
from uuid import uuid4

import pytest

from app.exceptions import AppError
from app.graph_kb.domain.constants import ENGINE_GRAPHRAG, ENGINE_LIGHTRAG, QUERY_NAIVE
from app.graph_kb.engine.fake_client import FakeGraphEngineClient
from app.graph_kb.engine.modes import map_query_mode
from app.graph_kb.engine.types import (
    ModelEndpoint,
    WorkerDocument,
    WorkerIndexRequest,
    WorkerQueryRequest,
)


def test_graphrag_rejects_naive() -> None:
    with pytest.raises(AppError) as exc:
        map_query_mode(ENGINE_GRAPHRAG, QUERY_NAIVE)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_fake_index_isolated_by_graph() -> None:
    client = FakeGraphEngineClient()
    llm = ModelEndpoint("http://x", "k", "m")
    a = uuid4()
    b = uuid4()
    w = uuid4()
    req_a = WorkerIndexRequest(
        workspace_id=w,
        graph_id=a,
        engine=ENGINE_LIGHTRAG,
        documents=[WorkerDocument(uuid4(), "a.txt", "alpha")],
        llm=llm,
        embedding=llm,
    )
    req_b = WorkerIndexRequest(
        workspace_id=w,
        graph_id=b,
        engine=ENGINE_LIGHTRAG,
        documents=[WorkerDocument(uuid4(), "b.txt", "beta")],
        llm=llm,
        embedding=llm,
    )
    await client.index(req_a)
    await client.index(req_b)
    qa = await client.query(
        WorkerQueryRequest(w, a, ENGINE_LIGHTRAG, "q", "local", 5)
    )
    assert "alpha" in qa.answer or qa.answer.startswith("fake:")
    export_b = await client.export_graph(engine=ENGINE_LIGHTRAG, workspace_id=w, graph_id=b)
    names = {e["name"] for e in export_b.entities}
    assert "alpha" not in names
```

Fake 的 `query.answer` 必须包含该图谱 index 过的文档文本（例如 `"fake:alpha"`），以便隔离断言。

- [ ] **Step 2–4:** 失败 → 实现 → PASS
- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/engine backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_graph_kb_engine_client.py
git commit -m "feat(graph-kb): add engine client protocol, fake, and HTTP adapter"
```

---

### Task 8: Celery 索引 / 清理 + 投影回写

**Files:**
- Create: `backend/app/graph_kb/service/index_service.py`
- Create: `backend/app/graph_kb/service/projection_service.py`
- Create: `backend/app/graph_kb/service/cleanup_service.py`
- Create: `backend/app/graph_kb/task/__init__.py`
- Create: `backend/app/graph_kb/task/index_task.py`
- Create: `backend/app/graph_kb/task/cleanup_task.py`
- Modify: `backend/app/celery_app.py`（确保 autodiscover `app.graph_kb.task`）
- Modify: `scripts/run-celery.cmd`、`scripts/run-celery.sh`：`MINERVA_CELERY_QUEUES` 默认 `default,dataset,graph_kb`
- Modify: `backend/.env.example` 注释
- Test: `backend/tests/test_graph_kb_index_service.py`

**Interfaces:**
- Consumes: `GraphEngineClient`；`resolve_graph_models`；文档文本加载
- Produces:
  - `async def enqueue_index(session, *, workspace_id, graph_id, user_id) -> GraphKbJob`：已有 pending/running 的 index/reindex → `AppError("graph_kb.job_conflict", "...", 409)`
  - `async def run_index_job(session, *, job_id)`：调 Worker `index`，`replace_projections`，成功则 `completed`，失败保留旧投影
  - `async def enqueue_cleanup(...)` / `async def run_cleanup_job`
  - `replace_projections(session, *, graph_id, workspace_id, export: GraphExport, summaries: list[SummaryItem])`：先删该 graph 三张投影表再插入

`index_task.py` 对齐 `dataset/task/indexing_task.py`：`@shared_task(bind=True, name=GRAPH_KB_INDEX_TASK_NAME)` + `asyncio.run`；`queue="graph_kb"`。

`celery_app.py` 查找现有 `autodiscover_tasks` 列表并加入 `"app.graph_kb.task"`。

`run_index_job` 入参给 Worker 的 `ModelEndpoint.api_key` 来自 `resolve_model`；写入 job.error 时调用 `redact_secret(key)`（只保留后 4 位或替换为 `***`）。

- [ ] **Step 1:** 单测 `enqueue_index` 冲突 409（用 Fake session 或纯函数 `assert_no_active_job(jobs)`）。

```python
from app.exceptions import AppError
from app.graph_kb.domain.constants import JOB_INDEX, STATUS_RUNNING
from app.graph_kb.service.index_service import assert_no_active_index_job


def test_conflict() -> None:
    try:
        assert_no_active_index_job([{"kind": JOB_INDEX, "status": STATUS_RUNNING}])
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "graph_kb.job_conflict"
    else:
        raise AssertionError("expected conflict")
```

再测 `replace_projections` 若需 DB 则标集成；至少测 `summaries_to_rows` 纯映射。

- [ ] **Step 2–4:** 实现 enqueue + task + projection → PASS
- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/service/index_service.py backend/app/graph_kb/service/projection_service.py backend/app/graph_kb/service/cleanup_service.py backend/app/graph_kb/task backend/app/celery_app.py scripts/run-celery.cmd scripts/run-celery.sh backend/.env.example backend/tests/test_graph_kb_index_service.py
git commit -m "feat(graph-kb): enqueue index/cleanup jobs and write projections"
```

DELETE 图谱改为：`delete_graph_sql` + `enqueue_cleanup`。

---

### Task 9: Query / 投影只读 API

**Files:**
- Create: `backend/app/graph_kb/service/query_service.py`
- Create: `backend/app/graph_kb/service/view_service.py`
- Modify: `backend/app/graph_kb/api/router.py`
- Test: `backend/tests/test_graph_kb_query.py`

**Interfaces:**
- Consumes: `map_query_mode`；`GraphEngineClient.query`；投影表
- Produces:
  - `async def query_graph(...) -> WorkerQueryResult`：`indexing_status != completed` → 409 `graph_kb.not_ready`；写入 `graph_kb_query`
  - `list_entities` / `list_relations` / `list_summaries`（读投影，分页 10）
  - `graph_view(*, seed_entity_id=None, hops=1|2, community_id=None)`：从投影做 BFS，默认 hops=1，最多返回 200 节点（常量 `GRAPH_VIEW_MAX_NODES = 200`）

Worker 503 向上抛，路由不捕获成 200。

- [ ] **Step 1:**

```python
from app.exceptions import AppError
from app.graph_kb.domain.constants import STATUS_PENDING
from app.graph_kb.service.query_service import assert_ready_for_query


def test_not_ready() -> None:
    try:
        assert_ready_for_query(STATUS_PENDING)
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "graph_kb.not_ready"
    else:
        raise AssertionError("expected 409")
```

`view_service.build_subgraph(entities, relations, *, seed_id, hops, max_nodes=200)` 纯函数单测：3 节点链只返回 hops=1 的 2 点 1 边。

- [ ] **Step 2–4:** 实现路由 GET/POST 与测试 → PASS
- [ ] **Step 5: Commit**

```bash
git add backend/app/graph_kb/service/query_service.py backend/app/graph_kb/service/view_service.py backend/app/graph_kb/api/router.py backend/tests/test_graph_kb_query.py
git commit -m "feat(graph-kb): add query, summaries, and subgraph view APIs"
```

---

### Task 10: LightRAG Worker 进程

**Files:**
- Create: `workers/graph-kb-lightrag/pyproject.toml`
- Create: `workers/graph-kb-lightrag/app/__init__.py`
- Create: `workers/graph-kb-lightrag/app/namespace.py`（复制主库公式，保持字符串一致）
- Create: `workers/graph-kb-lightrag/app/main.py`
- Create: `workers/graph-kb-lightrag/app/store.py`
- Create: `scripts/run-graph-kb-lightrag-worker.cmd`
- Test: `workers/graph-kb-lightrag/tests/test_namespace.py`

**Interfaces:**
- Consumes: JSON `{workspace_id, graph_id, ...}`；环境变量 `GRAPH_KB_LIGHTRAG_DATABASE_URL`、`GRAPH_KB_WORKER_FAKE`
- Produces: HTTP `POST /index` `/query` `/export_graph` `/list_summaries` `/delete_namespace`

`namespace.py` 必须与主库 `lightrag_workspace` 公式相同。请求若包含 `workspace` 字段 → **忽略**，只用两个 UUID。

`GRAPH_KB_WORKER_FAKE=1` 时不 import LightRAG，使用内存 dict（与 Fake 客户端行为一致），便于无 GPU/无 SDK 的 CI。

真实模式（`GRAPH_KB_WORKER_FAKE` 未开）：

```python
from lightrag import LightRAG, QueryParam
from lightrag.llm.openai import openai_complete_if_cache, openai_embed
```

用请求里的 `llm` / `embedding` 构造闭包（`base_url`、`api_key`、`model`）。`working_dir` 可用临时目录；KV/向量/图/doc 使用 PG 存储类，`workspace=lightrag_workspace(wid, gid)`。实例缓存：`dict[str, LightRAG]` key=workspace 字符串，进程内 LRU 最多 16。

`pyproject.toml`：`fastapi`、`uvicorn`、`pydantic`；真实引擎依赖 `lightrag-hku` 标 optional extra `engine`。

启动脚本：`uvicorn app.main:app --host 127.0.0.1 --port 8101`，工作目录 `workers/graph-kb-lightrag`。

- [ ] **Step 1:** Worker 包内 pytest：`lightrag_workspace` 与主库同一对 UUID 结果相同（把期望字符串写死，与 Task 1 测试一致）。
- [ ] **Step 2–4:** 实现 FastAPI + fake 模式 → `pytest workers/graph-kb-lightrag/tests -v` PASS
- [ ] **Step 5: Commit**

```bash
git add workers/graph-kb-lightrag scripts/run-graph-kb-lightrag-worker.cmd
git commit -m "feat(graph-kb): add isolated LightRAG worker process"
```

---

### Task 11: GraphRAG Worker 进程

**Files:**
- Create: `workers/graph-kb-graphrag/pyproject.toml`
- Create: `workers/graph-kb-graphrag/app/namespace.py`
- Create: `workers/graph-kb-graphrag/app/main.py`
- Create: `scripts/run-graph-kb-graphrag-worker.cmd`
- Test: `workers/graph-kb-graphrag/tests/test_root.py`

**Interfaces:**
- Consumes: `GRAPH_KB_DATA`；`workspace_id` + `graph_id` 拼 root；`GRAPH_KB_WORKER_FAKE`
- Produces: 与 Task 10 相同的 5 个 POST 路径，端口 **8102**

`graphrag_root` 与主库一致。禁止使用请求里的 `root` 字段。

Fake 模式写 `{root}/fake.json` 以便 `delete_namespace` 可删目录。

真实模式：把文档写入 `{root}/input/*.txt`，调用 `graphrag index --root {root}`（subprocess，timeout 用请求或默认 7200s），query 用 GraphRAG Python API `global_search` / `local_search`。`naive` 返回 HTTP 400。社区报告从 output parquet/json 读出映射为 `list_summaries`。

`pyproject.toml` optional extra `engine` = `graphrag`。

- [ ] **Step 1:** 单测 root 路径与 Task 1 期望一致；拒绝自定义 `root`。
- [ ] **Step 2–4:** 实现 → PASS
- [ ] **Step 5: Commit**

```bash
git add workers/graph-kb-graphrag scripts/run-graph-kb-graphrag-worker.cmd
git commit -m "feat(graph-kb): add isolated GraphRAG worker process"
```

---

### Task 12: 菜单、entitlement、前端壳与 API 客户端

**Files:**
- Modify: `backend/scripts/gen_sys_menu_seed_uuids.py`（在 `sub-dataset` 块后插入）
- Modify: `backend/sql/seeds/sys_menu_seed.sql`
- Create: `backend/sql/patches/2026-08-23-graph-kb-feature-menu.sql`
- Modify: `frontend/src/i18n/locales/zh-CN.json`、`en.json`
- Create: `frontend/src/features/graph-kb/api/graphKb.ts`
- Create: `frontend/src/features/graph-kb/index.ts`
- Modify: `frontend/src/app/router.tsx`

**Interfaces:**
- Consumes: 确定性 UUID
  - `sub-graph-kb` = `89803e0d-3455-5602-9bdd-55e138974154`
  - `graph-kb-list` = `13c654eb-10eb-524e-9f00-ef1cfb08ac62`
- Produces: 菜单「知识图谱」+ 子项「图谱」`/app/graph-kb`；`feature:graph_kb` 插入 `sys_permission`（与 `feature:dataset` 那次 patch 同结构）

`gen_sys_menu_seed_uuids.py` 增加：

```python
    ("sub-graph-kb", None, "知识图谱", "nav.graphKb", 5, None, "M", "ApartmentOutlined"),
    ("graph-kb-list", "sub-graph-kb", "图谱", "nav.graphKbList", 1, "/app/graph-kb", "C", "ApartmentOutlined"),
```

智能审核及之后的 `order_num` **不要**批量改（避免无谓 diff）；知识图谱与智能审核可同为 5。

i18n：

```json
"nav.graphKb": "知识图谱",
"nav.graphKbList": "图谱"
```

`graphKb.ts`：用现有 `apiClient`（与 `frontend/src/features/dataset/api` 相同 workspace 前缀）封装 spec §7.4 全部方法。分页 `page_size` 默认 `DEFAULT_PAGE_SIZE`。

`router.tsx` 增加：

```tsx
{ path: 'graph-kb', element: <GraphKbListPage /> },
{
  path: 'graph-kb/create',
  element: <GraphKbCreatePage />,
},
{
  path: 'graph-kb/:graphId',
  element: <GraphKbSectionLayout />,
  children: [
    { index: true, element: <Navigate to="documents" replace /> },
    { path: 'documents', element: <GraphKbDocumentsPage /> },
    { path: 'graph', element: <GraphKbGraphPage /> },
    { path: 'summaries', element: <GraphKbSummariesPage /> },
    { path: 'qa', element: <GraphKbQaPage /> },
    { path: 'settings', element: <GraphKbSettingsPage /> },
  ],
},
```

本 Task 页面可以是占位：根节点 `minerva-page-fill`，标题用 i18n。下一 Task 填实。

- [ ] **Step 1:** 前端不写失败单测；后端可测 `menu_key_to_feature("sub-graph-kb") == FEATURE_GRAPH_KB`（已在 Task 1 实现则补测）。

```python
from app.core.security.permission_codes import FEATURE_GRAPH_KB, menu_key_to_feature


def test_menu_maps_to_feature() -> None:
    assert menu_key_to_feature("sub-graph-kb") == FEATURE_GRAPH_KB
    assert menu_key_to_feature("graph-kb-list") == FEATURE_GRAPH_KB
```

- [ ] **Step 2–4:** 菜单 patch + 路由编译：`cd frontend && npx tsc --noEmit`（或项目现用的 `npm run build`）须通过
- [ ] **Step 5: Commit**

```bash
git add backend/scripts/gen_sys_menu_seed_uuids.py backend/sql/seeds/sys_menu_seed.sql backend/sql/patches/2026-08-23-graph-kb-feature-menu.sql frontend/src/features/graph-kb frontend/src/app/router.tsx frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json backend/tests/test_graph_kb_namespace.py
git commit -m "feat(graph-kb): add menu, feature entitlement, and frontend routes"
```

---

### Task 13: 前端列表、新建、文档、设置

**Files:**
- Create: `frontend/src/features/graph-kb/GraphKbListPage.tsx`
- Create: `frontend/src/features/graph-kb/GraphKbCreatePage.tsx`
- Create: `frontend/src/features/graph-kb/layout/GraphKbSectionLayout.tsx`
- Create: `frontend/src/features/graph-kb/documents/GraphKbDocumentsPage.tsx`
- Create: `frontend/src/features/graph-kb/settings/GraphKbSettingsPage.tsx`
- Modify: i18n

**Interfaces:**
- Consumes: `graphKb.ts`；`useAuth().workspaceId`；`listModelProviders`（与 Dataset 相同，筛 CHAT / EMBEDDINGS）
- Produces: 可用的建库与文档流（索引按钮调 `POST /index`，轮询 `GET /jobs/{id}`）

列表：Table `borderRadius` 走主题 4px；admin 显示「全部 / 仅我的」筛选（`mine_only` query）。删除 `Popconfirm`。

新建：Select 引擎（创建后不可改，设置页 disabled）；permission；成员多选（`partial_members` 时显示）；模型 Select `allowClear`。

文档页：Upload + TextArea 导入；索引进度 Tag。

设置：PATCH 名称/描述/permission/成员；引擎 Form.Item disabled。

Layout：左侧 Menu：documents / graph / summaries / qa / settings，对齐 `DatasetSectionLayout`。全页 Card 加 `minerva-page-shell-card`。

- [ ] **Step 1–4:** 实现后用浏览器走：无 workspace → 空态；有数据 → 列表分页 10。若无浏览器工具，`npm run build` 必须通过。
- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/graph-kb frontend/src/i18n/locales
git commit -m "feat(graph-kb): add list, create, documents, and settings pages"
```

---

### Task 14: 前端画布、摘要、问答

**Files:**
- Create: `frontend/src/features/graph-kb/graph/GraphKbGraphPage.tsx`
- Create: `frontend/src/features/graph-kb/graph/GraphKbCanvas.tsx`
- Create: `frontend/src/features/graph-kb/summaries/GraphKbSummariesPage.tsx`
- Create: `frontend/src/features/graph-kb/qa/GraphKbQaPage.tsx`
- Modify: `frontend/package.json`（加 `@antv/g6`）

**Interfaces:**
- Consumes: `GET .../entities|relations|graph-view|summaries`；`POST .../query`
- Produces: 表格 + G6 画布（仅渲染 `graph-view` 子图）；摘要树点击带 `community_id` 拉子图；问答 `mode` Select：`local|global|hybrid|naive`（引擎为 graphrag 时隐藏 naive）

`GraphKbCanvas`：容器 `height: 100%`、`border-radius: 4px`；节点 click 再请求 `hops=2`。禁止把全量 entities 一次塞进 G6。

空投影：Empty 态「请先完成索引」。

- [ ] **Step 1–4:** `npm run build` PASS；手动点问答至少一种 mode
- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/graph-kb frontend/package.json frontend/package-lock.json frontend/src/i18n/locales
git commit -m "feat(graph-kb): add subgraph canvas, summaries, and QA pages"
```

---

### Task 15: 隔离回归与 spec 回填

**Files:**
- Modify: `backend/tests/test_graph_kb_engine_client.py`（补交叉 workspace）
- Modify: `docs/superpowers/specs/2026-08-23-graph-kb-graphrag-lightrag-design.md` §11
- Modify: `README.md`（知识图谱小节：菜单、队列 `graph_kb`、两个 Worker 脚本）

**Interfaces:**
- Consumes: Fake client
- Produces: 文档与代码一致

交叉隔离测试：

```python
@pytest.mark.asyncio
async def test_cross_workspace_export_empty() -> None:
    client = FakeGraphEngineClient()
    llm = ModelEndpoint("http://x", "k", "m")
    w1, w2, g = uuid4(), uuid4(), uuid4()
    await client.index(
        WorkerIndexRequest(
            workspace_id=w1,
            graph_id=g,
            engine=ENGINE_LIGHTRAG,
            documents=[WorkerDocument(uuid4(), "a.txt", "secret-w1")],
            llm=llm,
            embedding=llm,
        )
    )
    export = await client.export_graph(
        engine=ENGINE_LIGHTRAG, workspace_id=w2, graph_id=g
    )
    assert export.entities == []
```

Fake 必须以 `(workspace_id, graph_id)` 为 key，不能只用 `graph_id`。

§11 实现对照改为真实路径；状态改为「部分实现」或「已实现」视完成度。

- [ ] **Step 1–4:** 测试 PASS；回填文档
- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_graph_kb_engine_client.py docs/superpowers/specs/2026-08-23-graph-kb-graphrag-lightrag-design.md README.md
git commit -m "docs(graph-kb): backfill implementation map and isolation tests"
```

---

## Self-review（对照 spec）

| spec 条目 | 任务 |
|-----------|------|
| 独立模块与菜单 | 5, 12 |
| 二选一引擎、创建后只读 | 4, 5, 13 |
| workspace+user ACL、admin 总览、超管无限制 | 2, 4 |
| 文件 + 纯文本 | 6, 13 |
| `sys_models` Chat/Embeddings | 6 |
| Worker 隔离、namespace 只在 Worker 拼 | 1, 7, 10, 11 |
| 不复用 mem0 Neo4j | 1 环境变量、10 |
| Celery `graph_kb`、投影、失败保留旧投影 | 8 |
| query mode 映射、409/503 | 7, 9 |
| 表格 + 子图画布 + 摘要 | 9, 14 |
| 删除顺序 + 异步 cleanup | 5, 8 |
| 小/中/大：异步 + 超时 + 画布封顶 200 节点 | 8, 9, 14 |
| 首期不做 Agent / 开放 API / Dataset 导入 / GraphRAG 增量 | 未列入任务 |

无 TBD。类型名全程：`GraphEngineClient`、`WorkerIndexRequest`、`GraphAclActor`、`FEATURE_GRAPH_KB`。
