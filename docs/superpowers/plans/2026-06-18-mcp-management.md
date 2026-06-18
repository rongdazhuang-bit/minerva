# MCP 连接管理 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付工作区隔离的 MCP 客户端/服务端配置 CRUD、Registry 运行时缓存、Agent 对话动态注册 MCP 工具，以及「智能体 > MCP」管理页。

**Architecture:** 分表 `sys_mcp_client` / `sys_mcp_server` + 单例 `McpRuntimeRegistry` 门面（启动预热、CRUD 立即 refresh、Agent 按 Run 短连接）；客户端保存前 `McpConnectionTester` 强制 handshake；服务端按 `exposure` JSON 挂载 `/mcp/s/{slug}`；环境变量 `MCP_CLIENT_ENABLED` / `MCP_SERVER_ENABLED` 控制运行时。

**Tech Stack:** FastAPI、SQLAlchemy 2 async、PostgreSQL JSONB、官方 `mcp` Python SDK、LangChain Tool 桥接、React + Ant Design + TanStack Query

**Spec:** [`docs/superpowers/specs/2026-06-18-mcp-management-design.md`](../specs/2026-06-18-mcp-management-design.md)

**注释:** 新增 Python 类/公开函数须遵守 `.cursor/skills/code-comments/SKILL.md`（类与方法 docstring）。

---

## File map

| 路径 | 动作 | 职责 |
|------|------|------|
| `backend/pyproject.toml` | 修改 | 添加 `mcp>=1.9` 依赖 |
| `backend/app/config.py` | 修改 | `MCP_CLIENT_ENABLED` 等三变量 |
| `backend/.env.example` | 修改 | 同步 env 文档 |
| `backend/.env.dev` | 修改 | 开发默认值 |
| `backend/sql/schema_postgresql.sql` | 修改 | 两表 DDL（无 FK） |
| `backend/sql/patches/2026-06-18-sys-mcp-tables.sql` | 创建 | 已有库增量 |
| `backend/app/mcp/domain/db/models.py` | 创建 | ORM |
| `backend/app/mcp/infrastructure/repository.py` | 创建 | 按 workspace 读写 |
| `backend/app/mcp/service/mcp_client_service.py` | 创建 | 客户端 CRUD + test gate |
| `backend/app/mcp/service/mcp_server_service.py` | 创建 | 服务端 CRUD + 引用校验 |
| `backend/app/mcp/runtime/connection_tester.py` | 创建 | handshake + list_tools |
| `backend/app/mcp/runtime/client_bridge.py` | 创建 | MCP → LangChain Tool |
| `backend/app/mcp/runtime/registry.py` | 创建 | 门面单例 |
| `backend/app/mcp/runtime/server_router.py` | 创建 | 对外 MCP 路由 |
| `backend/app/mcp/api/schemas.py` | 创建 | Pydantic |
| `backend/app/mcp/api/router.py` | 创建 | REST 端点 |
| `backend/app/core/infrastructure/db/bootstrap.py` | 修改 | 注册 ORM |
| `backend/app/core/api/router.py` | 修改 | include mcp router |
| `backend/app/main.py` | 修改 | lifespan 预热 Registry |
| `backend/app/agent/infrastructure/skill_loader.py` | 修改 | 合并 MCP 工具 |
| `backend/app/agent/service/agent_graph_run_service.py` | 修改 | Run 结束关闭 MCP sessions |
| `backend/scripts/gen_sys_menu_seed_uuids.py` | 修改 | 新增 `agents-mcp` 行 |
| `backend/sql/seeds/sys_menu_seed.sql` | 修改 | 重生成 |
| `backend/sql/patches/2026-06-18-agents-mcp-menu.sql` | 创建 | 已有库菜单 |
| `backend/tests/test_mcp_client_service.py` | 创建 | 服务层单测 |
| `backend/tests/test_mcp_api.py` | 创建 | API 集成测 |
| `frontend/src/api/mcp.ts` | 创建 | API 客户端 |
| `frontend/src/features/agent/mcp/AgentMcpPage.tsx` | 创建 | 管理 UI |
| `frontend/src/features/agent/mcp/AgentMcpPage.css` | 创建 | 样式 |
| `frontend/src/app/router.tsx` | 修改 | 路由 |
| `frontend/src/app/layout/AppBreadcrumb.tsx` | 修改 | 面包屑 |
| `frontend/src/i18n/locales/zh-CN.json` | 修改 | 文案 |
| `frontend/src/i18n/locales/en.json` | 修改 | 文案 |

---

### Task 1: 依赖与环境变量

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`

- [ ] **Step 1: 添加 MCP SDK 依赖**

在 `backend/pyproject.toml` 的 `dependencies` 数组末尾添加：

```toml
  "mcp>=1.9.0",
```

Run:

```bash
cd backend
pip install -e .
```

Expected: 无解析错误。

- [ ] **Step 2: 在 `Settings` 类中添加字段（放在 Agent 相关字段附近）**

```python
    mcp_client_enabled: bool = Field(
        default=False,
        description="When True, warm MCP client configs and register tools in Agent runs.",
        validation_alias=AliasChoices("MCP_CLIENT_ENABLED", "mcp_client_enabled"),
    )
    mcp_server_enabled: bool = Field(
        default=False,
        description="When True, mount outbound MCP server routes from sys_mcp_server.",
        validation_alias=AliasChoices("MCP_SERVER_ENABLED", "mcp_server_enabled"),
    )
    mcp_connect_timeout: int = Field(
        default=30,
        ge=5,
        le=300,
        description="Timeout seconds for MCP client test and run-time handshake.",
        validation_alias=AliasChoices("MCP_CONNECT_TIMEOUT", "mcp_connect_timeout"),
    )
```

- [ ] **Step 3: 同步 `.env.example` 与 `.env.dev`**

追加：

```env
MCP_CLIENT_ENABLED=false
MCP_SERVER_ENABLED=false
MCP_CONNECT_TIMEOUT=30
```

- [ ] **Step 4: Commit**

```bash
git add backend/pyproject.toml backend/app/config.py backend/.env.example backend/.env.dev
git commit -m "chore(mcp): add SDK dependency and env toggles"
```

---

### Task 2: 数据库表与 ORM

**Files:**
- Create: `backend/sql/patches/2026-06-18-sys-mcp-tables.sql`
- Modify: `backend/sql/schema_postgresql.sql`
- Create: `backend/app/mcp/domain/db/models.py`
- Create: `backend/app/mcp/domain/db/__init__.py`
- Create: `backend/app/mcp/__init__.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`

- [ ] **Step 1: 创建 patch SQL**

Create `backend/sql/patches/2026-06-18-sys-mcp-tables.sql`:

```sql
-- sys_mcp_client / sys_mcp_server（无库级外键）
CREATE TABLE IF NOT EXISTS public.sys_mcp_client (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  name          VARCHAR(128) NOT NULL,
  transport     VARCHAR(32)  NOT NULL,
  config        JSONB        NOT NULL DEFAULT '{}'::jsonb,
  secrets       JSONB        NOT NULL DEFAULT '{}'::jsonb,
  enabled       BOOLEAN      NOT NULL DEFAULT true,
  remark        VARCHAR(256) NULL,
  last_test_at  TIMESTAMPTZ  NULL,
  last_test_ok  BOOLEAN      NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_mcp_client_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_mcp_client_workspace_id
  ON public.sys_mcp_client (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_mcp_client_workspace_name
  ON public.sys_mcp_client (workspace_id, name);

CREATE TABLE IF NOT EXISTS public.sys_mcp_server (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  name          VARCHAR(128) NOT NULL,
  slug          VARCHAR(64)  NOT NULL,
  enabled       BOOLEAN      NOT NULL DEFAULT true,
  exposure      JSONB        NOT NULL DEFAULT '{}'::jsonb,
  auth_type     VARCHAR(32)  NOT NULL DEFAULT 'NONE',
  auth_secret   VARCHAR(512) NULL,
  remark        VARCHAR(256) NULL,
  create_at     TIMESTAMPTZ  NULL DEFAULT now(),
  update_at     TIMESTAMPTZ  NULL,
  CONSTRAINT sys_mcp_server_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_sys_mcp_server_workspace_id
  ON public.sys_mcp_server (workspace_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_mcp_server_slug
  ON public.sys_mcp_server (slug);
```

- [ ] **Step 2: 同步 `schema_postgresql.sql`**

在 `sys_ocr_tool` 表定义之后插入与 patch 等价的 `CREATE TABLE` + `COMMENT ON`（为每列写简短中文注释，风格与同文件一致）。

- [ ] **Step 3: 创建 ORM**

Create `backend/app/mcp/domain/db/models.py`:

```python
"""ORM for workspace-scoped MCP client and server configuration rows."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import sqlalchemy as sa
from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.infrastructure.db.base import Base


class SysMcpClient(Base):
    """External MCP server connection config for one workspace (Minerva acts as MCP client)."""

    __tablename__ = "sys_mcp_client"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    transport: Mapped[str] = mapped_column(String(32), nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    secrets: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    last_test_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_test_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    update_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class SysMcpServer(Base):
    """Outbound MCP server exposure config for one workspace."""

    __tablename__ = "sys_mcp_server"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=sa.true())
    exposure: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=sa.text("'{}'::jsonb"))
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, server_default="NONE")
    auth_secret: Mapped[str | None] = mapped_column(String(512), nullable=True)
    remark: Mapped[str | None] = mapped_column(String(256), nullable=True)
    create_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    update_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 4: 注册 bootstrap**

在 `bootstrap.py` 的 `_import_models()` 末尾添加：

```python
    import app.mcp.domain.db.models  # noqa: F401
```

- [ ] **Step 5: Commit**

```bash
git add backend/sql backend/app/mcp backend/app/core/infrastructure/db/bootstrap.py
git commit -m "feat(mcp): add sys_mcp_client and sys_mcp_server schema"
```

---

### Task 3: Repository 层

**Files:**
- Create: `backend/app/mcp/infrastructure/repository.py`
- Create: `backend/app/mcp/infrastructure/__init__.py`

- [ ] **Step 1: 实现仓储函数**

Create `backend/app/mcp/infrastructure/repository.py`，包含：

```python
async def list_clients_for_workspace(session, *, workspace_id: UUID) -> list[SysMcpClient]
async def get_client_for_workspace(session, *, workspace_id, client_id) -> SysMcpClient | None
async def list_enabled_clients_all_workspaces(session) -> list[SysMcpClient]
async def delete_clients_for_workspace(session, *, workspace_id) -> int

async def list_servers_for_workspace(session, *, workspace_id) -> list[SysMcpServer]
async def get_server_for_workspace(session, *, workspace_id, server_id) -> SysMcpServer | None
async def get_server_by_slug(session, *, slug: str) -> SysMcpServer | None
async def list_enabled_servers_all_workspaces(session) -> list[SysMcpServer]
async def count_servers_referencing_client(session, *, workspace_id, client_id) -> int
async def delete_servers_for_workspace(session, *, workspace_id) -> int
```

查询均带 `workspace_id` 过滤（除 `list_enabled_*_all_workspaces` 供 Registry 预热）。

- [ ] **Step 2: Commit**

```bash
git add backend/app/mcp/infrastructure/repository.py
git commit -m "feat(mcp): add repository helpers"
```

---

### Task 4: McpConnectionTester + 客户端 Service

**Files:**
- Create: `backend/app/mcp/runtime/connection_tester.py`
- Create: `backend/app/mcp/runtime/__init__.py`
- Create: `backend/app/mcp/service/mcp_client_service.py`
- Create: `backend/app/mcp/service/__init__.py`
- Create: `backend/tests/test_mcp_client_service.py`

- [ ] **Step 1: 编写 `McpConnectionTester`**

`connection_tester.py` 导出：

```python
@dataclass(frozen=True)
class McpTestResult:
    ok: bool
    tool_names: list[str]
    error_code: str | None = None
    error_message: str | None = None

class McpConnectionTester:
    async def test(self, *, transport: str, config: dict, secrets: dict) -> McpTestResult:
        ...
```

实现要点：
- `STDIO`：用 `mcp.client.stdio.stdio_client` + `StdioServerParameters(command, args, env, cwd)`
- `SSE`：`mcp.client.sse.sse_client(url, headers=...)`
- `STREAMABLE_HTTP`：`mcp.client.streamable_http.streamablehttp_client(url, headers=...)`
- 使用 `asyncio.wait_for(..., timeout=settings.mcp_connect_timeout)`
- 成功：session 内 `list_tools()`，返回 tool name 列表
- 失败：映射为 `mcp.client_connect_failed` / `mcp.client_connect_timeout` / `mcp.client_stdio_failed`

- [ ] **Step 2: 编写 `mcp_client_service.py`**

核心函数：

```python
async def test_client_connection(...) -> McpTestResult
async def create_client(..., skip_test: bool = False) -> SysMcpClient  # skip_test 仅测试用
async def update_client(...) -> SysMcpClient
async def delete_client(...) -> None
async def list_clients(...) -> list[SysMcpClient]
async def get_client(...) -> SysMcpClient
```

`create_client` / `update_client` 流程：
1. 校验 `transport` ∈ `{STDIO, SSE, STREAMABLE_HTTP}` 且 config 字段齐全
2. 调用 `test_client_connection`；`ok=False` → `raise AppError(..., 422)`
3. persist，`last_test_at=now`, `last_test_ok=True`
4. `mcp_registry.refresh_workspace_clients(workspace_id)`

重名：同 workspace `name` 冲突 → `409 mcp.client_name_duplicate`

- [ ] **Step 3: 编写单测（mock tester）**

Create `backend/tests/test_mcp_client_service.py`：

```python
@pytest.mark.asyncio
async def test_create_client_rejects_when_test_fails(monkeypatch):
    async def fake_test(**kwargs):
        return McpTestResult(ok=False, tool_names=[], error_code="mcp.client_connect_failed")
    monkeypatch.setattr("app.mcp.service.mcp_client_service.McpConnectionTester.test", fake_test)
    with pytest.raises(AppError) as exc:
        await create_client(session, workspace_id=ws_id, ...)
    assert exc.value.code == "mcp.client_connect_failed"
```

Run:

```bash
cd backend
pytest tests/test_mcp_client_service.py -v
```

Expected: PASS（需项目已配置 pytest + async fixtures；若无 `conftest.py`，本 Task 内创建最小 `backend/tests/conftest.py` 提供 `session` fixture 或标记 `@pytest.mark.skip` 并改用 httpx 集成测于 Task 6）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/runtime backend/app/mcp/service backend/tests
git commit -m "feat(mcp): client service with mandatory connection test"
```

---

### Task 5: McpRuntimeRegistry 门面

**Files:**
- Create: `backend/app/mcp/runtime/registry.py`
- Modify: `backend/app/mcp/runtime/client_bridge.py`（同 Task 内创建）

- [ ] **Step 1: 定义 snapshot 与单例**

```python
@dataclass(frozen=True)
class McpClientSnapshot:
    id: UUID
    workspace_id: UUID
    name: str
    transport: str
    config: dict
    secrets: dict
    enabled: bool

@dataclass(frozen=True)
class McpServerSnapshot:
    id: UUID
    workspace_id: UUID
    slug: str
    enabled: bool
    exposure: dict
    auth_type: str
    auth_secret: str | None

class McpRuntimeRegistry:
    _instance: McpRuntimeRegistry | None = None

    @classmethod
    def get(cls) -> McpRuntimeRegistry: ...

    async def warm_from_db(self, session: AsyncSession) -> None: ...
    def refresh_workspace_clients(self, workspace_id: UUID, rows: list[McpClientSnapshot]) -> None: ...
    def refresh_workspace_servers(self, workspace_id: UUID, rows: list[McpServerSnapshot]) -> None: ...
    def list_client_snapshots(self, workspace_id: UUID) -> list[McpClientSnapshot]: ...
    def list_server_snapshots(self) -> list[McpServerSnapshot]: ...
```

模块级：`mcp_registry = McpRuntimeRegistry.get()`

- [ ] **Step 2: `client_bridge.py` — MCP tools → LangChain**

```python
def mcp_tool_name(client_name: str, original: str) -> str:
    safe = re.sub(r"[^a-z0-9]+", "_", client_name.lower()).strip("_")
    return f"mcp__{safe}__{original}"

async def load_langchain_tools_for_workspace(
    workspace_id: UUID,
    *,
    session_factory,
) -> tuple[list[BaseTool], list[Any]]:
    """Return (tools, open_sessions) — caller must close sessions after run."""
```

每个 enabled client：连接 → `list_tools` → 为每个 tool 包装 `@tool` 异步 callable（内部 `call_tool`）。

- [ ] **Step 3: Registry 调用 bridge**

```python
async def resolve_langchain_tools(self, workspace_id: UUID, session_factory) -> tuple[list, list]:
    if not settings.mcp_client_enabled:
        return [], []
    ...
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/runtime/registry.py backend/app/mcp/runtime/client_bridge.py
git commit -m "feat(mcp): runtime registry and client bridge"
```

---

### Task 6: MCP REST API（客户端 + runtime-status）

**Files:**
- Create: `backend/app/mcp/api/schemas.py`
- Create: `backend/app/mcp/api/router.py`
- Create: `backend/app/mcp/api/__init__.py`
- Modify: `backend/app/core/api/router.py`
- Create: `backend/tests/test_mcp_api.py`

- [ ] **Step 1: Pydantic schemas**

```python
class McpClientCreateIn(BaseModel):
    name: str
    transport: Literal["STDIO", "SSE", "STREAMABLE_HTTP"]
    config: dict[str, Any]
    secrets: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    remark: str | None = None

class McpClientListItemOut(BaseModel):
    id: UUID
    name: str
    transport: str
    enabled: bool
    last_test_at: datetime | None
    last_test_ok: bool | None
    has_secrets: bool
    ...

class McpRuntimeStatusOut(BaseModel):
    client_enabled: bool
    server_enabled: bool
```

列表/详情响应 **不返回** secrets 明文；仅 `has_secrets: bool`。

- [ ] **Step 2: Router 端点**

前缀：`/workspaces/{workspace_id}/mcp`

| 路由 | Depends |
|------|---------|
| GET `/runtime-status` | `require_workspace_member` |
| GET/POST/PATCH/DELETE `/clients...` | 读 member / 写 `require_workspace_owner_or_admin` |
| POST `/clients/test` | owner/admin |

`POST /clients/test` body 同 create，不落库，直接返回 `{ ok, tool_names, error_code?, error_message? }`。

- [ ] **Step 3: 挂载到 `app/core/api/router.py`**

```python
from app.mcp.api.router import router as mcp_router
api.include_router(mcp_router)
```

- [ ] **Step 4: API 集成测**

`test_mcp_api.py` 覆盖：
- member 调 POST `/clients` → 403
- owner/admin mock test 成功 → 201
- test 失败 → 422

- [ ] **Step 5: Commit**

```bash
git add backend/app/mcp/api backend/app/core/api/router.py backend/tests/test_mcp_api.py
git commit -m "feat(mcp): client REST API and runtime-status"
```

---

### Task 7: MCP 服务端 Service + API

**Files:**
- Create: `backend/app/mcp/service/mcp_server_service.py`
- Modify: `backend/app/mcp/api/schemas.py`
- Modify: `backend/app/mcp/api/router.py`

- [ ] **Step 1: exposure 校验 helper**

```python
def validate_exposure(session, *, workspace_id, exposure: dict) -> None:
    # include_all_builtin / builtin_skills → skill in list_indexed_skill_ids()
    # mcp_client_ids → repo.get_client_for_workspace 存在且 enabled
```

- [ ] **Step 2: server service CRUD**

```python
async def create_server(...) -> SysMcpServer:
    validate_slug(slug)  # regex + global unique
    validate_exposure(...)
    persist
    mcp_registry.refresh_workspace_servers(...)
    return row

async def delete_client(...):
    if await repo.count_servers_referencing_client(...) > 0:
        raise AppError("mcp.client_in_use", ..., 409)
```

**不测外部连通性**（spec §6.2）。

- [ ] **Step 3: Router `/servers` CRUD**

- [ ] **Step 4: Commit**

```bash
git add backend/app/mcp/service/mcp_server_service.py backend/app/mcp/api
git commit -m "feat(mcp): server CRUD with exposure validation"
```

---

### Task 8: 对外 MCP Server 路由 + lifespan 预热

**Files:**
- Create: `backend/app/mcp/runtime/server_router.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: `server_router.py`**

```python
def mount_mcp_server_routes(app: FastAPI, registry: McpRuntimeRegistry) -> None:
    """Register /mcp/s/{slug} handlers for each enabled server snapshot when MCP_SERVER_ENABLED."""
```

每个 slug：
- 校验 Bearer / X-API-Key（按 snapshot.auth_type）
- 按 `exposure` 组装 tool 列表：
  - builtin：调用 `load_tools_for_skill(skill_id, SkillToolContext(workspace_id=...))`
  - clients：复用 `client_bridge` 连接外部 MCP 并聚合 tools
- 使用 `mcp.server` SDK 暴露 Streamable HTTP（SSE 可作为同路由协商）

- [ ] **Step 2: 修改 `main.py` lifespan**

```python
from app.mcp.runtime.registry import mcp_registry

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_missing_tables()
    await bootstrap_sys_menu_seed()
    if settings.mcp_client_enabled or settings.mcp_server_enabled:
        from app.dependencies import async_session_factory
        async with async_session_factory() as session:
            await mcp_registry.warm_from_db(session)
    if settings.mcp_server_enabled:
        from app.mcp.runtime.server_router import mount_mcp_server_routes
        mount_mcp_server_routes(app, mcp_registry)
    yield
    await close_langgraph_checkpointer()
```

`warm_from_db`：分别调用 `list_enabled_clients_all_workspaces` / `list_enabled_servers_all_workspaces` 填充内存。

服务端 CRUD 后调用 `mount_mcp_server_routes` 重新挂载（可先 `clear` 旧路由或使用可热更新的 handler 表）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/mcp/runtime/server_router.py backend/app/main.py
git commit -m "feat(mcp): lifespan warm registry and mount server routes"
```

---

### Task 9: Agent 对话集成

**Files:**
- Modify: `backend/app/agent/infrastructure/skill_loader.py`
- Modify: `backend/app/agent/service/agent_graph_run_service.py`
- Modify: `backend/app/agent/graphs/deps.py`（如需存放 open sessions）

- [ ] **Step 1: 扩展 `build_skill_react_agent`**

在 `tools = load_tools_for_skill(sid, ctx)` 之后：

```python
from app.config import settings
from app.mcp.runtime.registry import mcp_registry

mcp_sessions: list = []
if settings.mcp_client_enabled:
    mcp_tools, mcp_sessions = await mcp_registry.resolve_langchain_tools(
        ctx.workspace_id, session_factory=...
    )
    tools = _merge_tools_by_name(tools, mcp_tools)
```

将 `build_skill_react_agent` 改为 `async def`（调用链：`executor` → `build_skill_react_agent` 一并改 async）。

`_merge_tools_by_name`：后出现的同名 tool 跳过并 log warning。

- [ ] **Step 2: Run 生命周期关闭 sessions**

在 `AgentGraphRunService` 的 run finally 块：

```python
for sess in deps.mcp_sessions:
    await sess.close()  # 或 SDK 等价 cleanup
```

连接失败时：`log.warning` + 可选 SSE（若已有扩展点则发 `mcp.tools_unavailable`）；不 raise。

- [ ] **Step 3: 配置变更失效 sub-agent 缓存**

在 `mcp_client_service` refresh 后：

```python
from app.agent.infrastructure.skill_loader import invalidate_subagent_cache_for_workspace
invalidate_subagent_cache_for_workspace(workspace_id)  # 新增：清空 build_skill_react_agent cache 中该 ws 的条目
```

在 `skill_loader.py` 增加模块级 `_subagent_cache: dict` 与 invalidation helper（当前 cache 在 `build_skill_react_agent` 参数传入；若 cache 在 deps 层，则在 deps 上清理）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent
git commit -m "feat(mcp): register workspace MCP tools in agent runs"
```

---

### Task 10: 菜单种子与 patch

**Files:**
- Modify: `backend/scripts/gen_sys_menu_seed_uuids.py`
- Modify: `backend/sql/seeds/sys_menu_seed.sql`（运行脚本生成）
- Create: `backend/sql/patches/2026-06-18-agents-mcp-menu.sql`

- [ ] **Step 1: 在 `ROWS` 中 `agents-memory` 之后插入**

```python
    ("agents-mcp", "sub-agents", "MCP", "nav.agentsMcp", 4, "/app/agents/mcp", "C", "ApiOutlined"),
```

并将原 `agents-memory` 的 order 保持 3（MCP 为 4）。

- [ ] **Step 2: 重生成 seed**

```bash
cd backend
python scripts/gen_sys_menu_seed_uuids.py
```

- [ ] **Step 3: 创建 patch（使用脚本输出的 UUID）**

```sql
INSERT INTO public.sys_menu (
  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status
) VALUES (
  '<agents-mcp-uuid>', '<sub-agents-uuid>', 'MCP', 'nav.agentsMcp', 'agents-mcp', 4,
  '/app/agents/mcp', 'C', 'ApiOutlined', true, true
) ON CONFLICT (id) DO NOTHING;
```

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/gen_sys_menu_seed_uuids.py backend/sql/seeds/sys_menu_seed.sql backend/sql/patches/2026-06-18-agents-mcp-menu.sql
git commit -m "feat(mcp): add agents MCP menu seed and patch"
```

---

### Task 11: 前端 API 与管理页

**Files:**
- Create: `frontend/src/api/mcp.ts`
- Create: `frontend/src/features/agent/mcp/AgentMcpPage.tsx`
- Create: `frontend/src/features/agent/mcp/AgentMcpPage.css`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: `mcp.ts` API 封装**

```typescript
export type McpTransport = 'STDIO' | 'SSE' | 'STREAMABLE_HTTP'

export async function listMcpClients(workspaceId: string): Promise<McpClientListItem[]>
export async function testMcpClient(workspaceId: string, body: McpClientCreateBody): Promise<McpTestResult>
export async function createMcpClient(workspaceId: string, body: McpClientCreateBody): Promise<McpClientDetail>
// ... servers 同理
export async function getMcpRuntimeStatus(workspaceId: string): Promise<{ client_enabled: boolean; server_enabled: boolean }>
```

- [ ] **Step 2: `AgentMcpPage.tsx`**

结构（参考 `OcrSettingsPage.tsx`）：
- `Tabs`: `clients` | `servers`
- 各 Tab：`Table` + `Drawer` + `Popconfirm` 删除
- 客户端 Drawer：`Select` transport → 条件字段
- 保存：`await testMcpClient()` → 成功后再 `create/patch`
- 顶栏 Alert：读取 `runtime-status`，未启用时提示

- [ ] **Step 3: i18n**

```json
"nav.agentsMcp": "MCP",
"mcp.clients.tab": "MCP 客户端",
"mcp.servers.tab": "MCP 服务端",
"mcp.testBeforeSave": "保存前将验证连通性",
"mcp.clientDisabledBanner": "MCP 客户端未启用，配置仅存储，对话中不会加载。",
...
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/mcp.ts frontend/src/features/agent/mcp frontend/src/i18n
git commit -m "feat(mcp): management UI with test-before-save"
```

---

### Task 12: 路由、面包屑与 spec 回填

**Files:**
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/layout/AppBreadcrumb.tsx`
- Modify: `frontend/src/app/layout/AppLayout.tsx`（若 MCP 页需 `overflow: hidden`）
- Modify: `docs/superpowers/specs/2026-06-18-mcp-management-design.md`

- [ ] **Step 1: 注册路由**

在 `router.tsx` agents 段添加：

```tsx
{ path: 'agents/mcp', element: <AgentMcpPage /> },
```

- [ ] **Step 2: 面包屑**

在 `agentsBreadcrumb` 中：

```typescript
if (pathname.startsWith('/app/agents/mcp')) {
  return [home, agentsBase, { title: t('nav.agentsMcp') }]
}
```

- [ ] **Step 3: 手动冒烟**

1. 执行 SQL patch 或依赖 `AUTO_CREATE_TABLES`
2. 设置 `MCP_CLIENT_ENABLED=true`，重启 backend
3. owner 登录 → 智能体 → MCP → 创建 stdio 客户端（test 通过）
4. Agent 对话发送消息，trace 中出现 `mcp__*` 工具调用

- [ ] **Step 4: 回填 spec §12 实现对照**

更新表格「状态」列为「已实现」并填写实际文件路径。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/app docs/superpowers/specs/2026-06-18-mcp-management-design.md
git commit -m "feat(mcp): wire routes and update spec implementation table"
```

---

## Plan self-review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| 分表 + Registry 门面 | Task 2, 5, 8 |
| 三 transport | Task 4 |
| 客户端保存前 test | Task 4, 6, 11 |
| 服务端 exposure 可配置 | Task 7, 8 |
| env 开关 + 启动预热 | Task 1, 8 |
| CRUD 立即 refresh | Task 4, 7 |
| Agent 动态注册 | Task 9 |
| 菜单 MCP | Task 10, 12 |
| 权限 owner/admin 写 | Task 6, 7 |
| 删除 client 409 | Task 7 |
| runtime-status | Task 6, 11 |
| Popconfirm 删除 | Task 11 |
| .env 同步 | Task 1 |
| 无 FK | Task 2 |

无 TBD / 占位步骤。

---

## Execution handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-18-mcp-management.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间做 review，迭代快  
2. **Inline Execution** — 在本会话按 Task 顺序直接实现，批次间设检查点

你选哪种？
