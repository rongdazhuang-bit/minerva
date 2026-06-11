# 租户管理（sys_tenants + sys_workspaces）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现平台超管专用的租户 CRUD、嵌套工作空间 CRUD（Drawer），扩展 `sys_tenants` / `sys_workspaces` 字段，并在设置页新增「租户管理」菜单与完整 UI。

**Architecture:** 后端新建 `app/sys/tenant/` 分层（对齐 `app/sys/role`）；ORM 扩展 `identity/models.py` 的 `Tenant`/`Workspace`；全局路由 `/sys/tenants` + `/sys/tenants/{tenant_id}/workspaces`；鉴权 `require_super_admin`；前端 `TenantsPage` + `TenantFormDrawer` + `WorkspaceDrawer`（内容区 `minerva-scrollbar-thin`）。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, PostgreSQL, pytest, React 18, Ant Design, TypeScript, react-i18next, @tanstack/react-query。

**设计文档：** `docs/superpowers/specs/2026-06-11-tenant-management-design.md`

---

## File Structure

### Backend（新建）

| 文件 | 职责 |
|------|------|
| `backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql` | ALTER 两表增列 |
| `backend/sql/patches/2026-06-11-sys-tenant-menu.sql` | 菜单 UPSERT + 字典 order_num |
| `backend/app/sys/tenant/__init__.py` | 包标记 |
| `backend/app/sys/tenant/api/deps.py` | `require_super_admin` |
| `backend/app/sys/tenant/api/schemas.py` | Pydantic 入参/出参 |
| `backend/app/sys/tenant/api/router.py` | 10 个端点 |
| `backend/app/sys/tenant/infrastructure/repository.py` | 分页查询、写入、级联删 |
| `backend/app/sys/tenant/service/tenant_service.py` | slug 校验、业务编排 |
| `backend/tests/test_tenant_service.py` | service 单元测试 |
| `backend/tests/test_tenant_api.py` | 租户 API 鉴权/路由测试 |
| `backend/tests/test_tenant_workspace_api.py` | 工作空间嵌套 API 测试 |

### Backend（修改）

| 文件 | 变更 |
|------|------|
| `backend/sql/schema_postgresql.sql` | `sys_tenants` / `sys_workspaces` 增列 |
| `backend/sql/seeds/sys_menu_seed.sql` | 租户管理节点 + 字典 order_num=10 |
| `backend/app/core/domain/identity/models.py` | `Tenant`/`Workspace` 新字段 |
| `backend/app/core/api/router.py` | `include_router(tenants_router)` |

### Frontend（新建）

| 文件 | 职责 |
|------|------|
| `frontend/src/api/tenants.ts` | API 客户端与类型 |
| `frontend/src/features/settings/tenants/TenantsPage.tsx` | 租户分页列表 |
| `frontend/src/features/settings/tenants/TenantsPage.css` | 布局/滚动 |
| `frontend/src/features/settings/tenants/TenantFormDrawer.tsx` | 租户新增/编辑 |
| `frontend/src/features/settings/tenants/WorkspaceDrawer.tsx` | 工作空间 Drawer CRUD |
| `frontend/src/features/settings/tenants/index.ts` | barrel export |

### Frontend（修改）

| 文件 | 变更 |
|------|------|
| `frontend/src/app/router.tsx` | 注册 `settings/tenants` |
| `frontend/src/app/layout/AppBreadcrumb.tsx` | breadcrumb |
| `frontend/src/i18n/locales/zh-CN.json` | `settings.tenants`、`tenants.*` |
| `frontend/src/i18n/locales/en.json` | 同上英文 |

---

### Task 1: SQL 迁移（表扩展）

**Files:**
- Create: `backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 编写 patch**

`backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql`：

```sql
-- 已有库增量：sys_tenants / sys_workspaces 扩展字段
ALTER TABLE public.sys_tenants
  ADD COLUMN IF NOT EXISTS status BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS remark VARCHAR(500) NULL,
  ADD COLUMN IF NOT EXISTS create_at TIMESTAMPTZ NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at TIMESTAMPTZ NULL;

ALTER TABLE public.sys_workspaces
  ADD COLUMN IF NOT EXISTS status BOOLEAN NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS remark VARCHAR(500) NULL,
  ADD COLUMN IF NOT EXISTS create_at TIMESTAMPTZ NULL DEFAULT now(),
  ADD COLUMN IF NOT EXISTS update_at TIMESTAMPTZ NULL;

COMMENT ON COLUMN public.sys_tenants.status IS 'true=正常 false=停用';
COMMENT ON COLUMN public.sys_tenants.remark IS '备注';
COMMENT ON COLUMN public.sys_tenants.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_tenants.update_at IS '修改时间';
COMMENT ON COLUMN public.sys_workspaces.status IS 'true=正常 false=停用';
COMMENT ON COLUMN public.sys_workspaces.remark IS '备注';
COMMENT ON COLUMN public.sys_workspaces.create_at IS '创建时间';
COMMENT ON COLUMN public.sys_workspaces.update_at IS '修改时间';
```

- [ ] **Step 2: 更新 `schema_postgresql.sql` 中 `sys_tenants` / `sys_workspaces` CREATE 块**

将两表定义改为含 `status`、`remark`、`create_at`、`update_at`（与 patch 一致）。

- [ ] **Step 3: Commit**

```bash
git add backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql backend/sql/schema_postgresql.sql
git commit -m "feat(tenant): extend sys_tenants and sys_workspaces columns"
```

---

### Task 2: ORM 扩展

**Files:**
- Modify: `backend/app/core/domain/identity/models.py`

- [ ] **Step 1: 扩展 `Tenant` 模型**

在 `Tenant` 类中追加（import 已有 `Boolean`, `DateTime`, `text`）：

```python
status: Mapped[bool] = mapped_column(
    Boolean, nullable=False, server_default=sa.true()
)
remark: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
create_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), server_default=text("now()"), nullable=True
)
update_at: Mapped[Optional[datetime]] = mapped_column(
    DateTime(timezone=True), nullable=True
)
```

- [ ] **Step 2: 扩展 `Workspace` 模型**

同上四个字段。

- [ ] **Step 3: Commit**

```bash
git add backend/app/core/domain/identity/models.py
git commit -m "feat(tenant): add status and audit fields to Tenant and Workspace ORM"
```

---

### Task 3: Repository 层

**Files:**
- Create: `backend/app/sys/tenant/infrastructure/repository.py`
- Create: `backend/app/sys/tenant/infrastructure/__init__.py`

- [ ] **Step 1: 实现 repository**

关键函数（完整实现，含 docstring）：

```python
"""Persistence helpers for sys_tenants and sys_workspaces."""

from __future__ import annotations

import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import (
    Tenant,
    TenantMembership,
    Workspace,
    WorkspaceMembership,
)


async def count_tenants_page(
    session: AsyncSession,
    *,
    name: str | None,
    status: bool | None,
) -> int:
    """Count tenants matching optional filters."""

    stmt = select(func.count()).select_from(Tenant)
    if name:
        stmt = stmt.where(Tenant.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Tenant.status == status)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def list_tenants_page(
    session: AsyncSession,
    *,
    name: str | None,
    status: bool | None,
    offset: int,
    limit: int,
) -> list[Tenant]:
    """Return one page of tenants ordered by create_at DESC."""

    stmt = select(Tenant)
    if name:
        stmt = stmt.where(Tenant.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Tenant.status == status)
    stmt = stmt.order_by(Tenant.create_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_tenant(session: AsyncSession, *, tenant_id: uuid.UUID) -> Tenant | None:
    """Load tenant by primary key."""

    return await session.get(Tenant, tenant_id)


async def count_workspaces_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str | None,
    status: bool | None,
) -> int:
    """Count workspaces under a tenant."""

    stmt = (
        select(func.count())
        .select_from(Workspace)
        .where(Workspace.tenant_id == tenant_id)
    )
    if name:
        stmt = stmt.where(Workspace.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Workspace.status == status)
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def list_workspaces_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    name: str | None,
    status: bool | None,
    offset: int,
    limit: int,
) -> list[Workspace]:
    """Return one page of workspaces for a tenant."""

    stmt = select(Workspace).where(Workspace.tenant_id == tenant_id)
    if name:
        stmt = stmt.where(Workspace.name.ilike(f"%{name}%"))
    if status is not None:
        stmt = stmt.where(Workspace.status == status)
    stmt = stmt.order_by(Workspace.create_at.desc()).offset(offset).limit(limit)
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_workspace_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> Workspace | None:
    """Load workspace when it belongs to tenant_id."""

    stmt = select(Workspace).where(
        Workspace.id == workspace_id,
        Workspace.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def delete_tenant_cascade(session: AsyncSession, *, tenant_id: uuid.UUID) -> None:
    """Delete tenant memberships, workspace memberships, workspaces, then tenant."""

    ws_ids = (
        await session.execute(
            select(Workspace.id).where(Workspace.tenant_id == tenant_id)
        )
    ).scalars().all()
    if ws_ids:
        await session.execute(
            delete(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id.in_(ws_ids)
            )
        )
    await session.execute(
        delete(TenantMembership).where(TenantMembership.tenant_id == tenant_id)
    )
    await session.execute(delete(Workspace).where(Workspace.tenant_id == tenant_id))
    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))


async def delete_workspace_row(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> int:
    """Delete only the sys_workspaces row; return rows affected."""

    result = await session.execute(
        delete(Workspace).where(
            Workspace.id == workspace_id,
            Workspace.tenant_id == tenant_id,
        )
    )
    return result.rowcount or 0
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/tenant/
git commit -m "feat(tenant): add tenant and workspace repository"
```

---

### Task 4: Service 层 + 单元测试

**Files:**
- Create: `backend/app/sys/tenant/service/tenant_service.py`
- Create: `backend/app/sys/tenant/service/__init__.py`
- Create: `backend/tests/test_tenant_service.py`

- [ ] **Step 1: 编写 failing test `test_validate_slug_rejects_uppercase`**

```python
"""Unit tests for tenant_service slug validation."""

import pytest

from app.exceptions import AppError
from app.sys.tenant.service import tenant_service as svc


def test_validate_slug_rejects_uppercase() -> None:
    """Uppercase slug is invalid."""

    with pytest.raises(AppError) as exc:
        svc.validate_slug("My-Tenant")
    assert exc.value.code == "tenant.invalid_slug"
```

- [ ] **Step 2: 运行确认 FAIL**

Run: `cd backend && pytest tests/test_tenant_service.py::test_validate_slug_rejects_uppercase -v`  
Expected: FAIL — `validate_slug` not defined

- [ ] **Step 3: 实现 `tenant_service.py` 核心逻辑**

```python
"""Platform super-admin tenant and workspace management."""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import Tenant, Workspace
from app.exceptions import AppError
from app.sys.tenant.infrastructure import repository as repo

_SLUG_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$")


def _utc_now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(UTC)


def validate_slug(slug: str, *, code_prefix: str = "tenant") -> str:
    """Normalize and validate slug; raise AppError on invalid format."""

    normalized = slug.strip().lower()
    if not _SLUG_RE.fullmatch(normalized):
        raise AppError(
            f"{code_prefix}.invalid_slug",
            "Invalid slug format",
            400,
        )
    return normalized


def _is_unique_violation(exc: IntegrityError) -> bool:
    """True when the DB error is a unique constraint violation."""

    orig = getattr(exc, "orig", None)
    if orig is not None and getattr(orig, "pgcode", None) == "23505":
        return True
    return "unique" in str(exc).lower()


async def _commit_or_conflict(
    session: AsyncSession,
    *,
    code: str,
) -> None:
    """Commit or map unique violations to conflict error."""

    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        if _is_unique_violation(e):
            raise AppError(code, "Duplicate slug", 409) from e
        raise


async def _require_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> Tenant:
    """Load tenant or raise tenant.not_found."""

    row = await repo.get_tenant(session, tenant_id=tenant_id)
    if row is None:
        raise AppError("tenant.not_found", "Tenant not found", 404)
    return row


async def list_tenants_page(
    session: AsyncSession,
    *,
    page: int,
    page_size: int,
    name: str | None = None,
    status: bool | None = None,
) -> tuple[list[Tenant], int]:
    """Return paginated tenants."""

    total = await repo.count_tenants_page(session, name=name, status=status)
    offset = (page - 1) * page_size
    rows = await repo.list_tenants_page(
        session, name=name, status=status, offset=offset, limit=page_size
    )
    return rows, total


async def create_tenant(session: AsyncSession, payload: dict[str, Any]) -> Tenant:
    """Create a tenant row."""

    slug = validate_slug(str(payload["slug"]), code_prefix="tenant")
    row = Tenant(
        name=str(payload["name"]).strip(),
        slug=slug,
        status=bool(payload.get("status", True)),
        remark=payload.get("remark"),
    )
    session.add(row)
    await _commit_or_conflict(session, code="tenant.conflict")
    await session.refresh(row)
    return row


async def patch_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: dict[str, Any],
) -> Tenant:
    """Partially update a tenant."""

    row = await _require_tenant(session, tenant_id=tenant_id)
    if "name" in payload and payload["name"] is not None:
        row.name = str(payload["name"]).strip()
    if "slug" in payload and payload["slug"] is not None:
        row.slug = validate_slug(str(payload["slug"]), code_prefix="tenant")
    if "status" in payload and payload["status"] is not None:
        row.status = bool(payload["status"])
    if "remark" in payload:
        row.remark = payload["remark"]
    row.update_at = _utc_now()
    await _commit_or_conflict(session, code="tenant.conflict")
    await session.refresh(row)
    return row


async def delete_tenant(session: AsyncSession, *, tenant_id: uuid.UUID) -> None:
    """Cascade-delete tenant and related membership/workspace rows."""

    await _require_tenant(session, tenant_id=tenant_id)
    await repo.delete_tenant_cascade(session, tenant_id=tenant_id)
    await session.commit()


async def list_workspaces_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    page: int,
    page_size: int,
    name: str | None = None,
    status: bool | None = None,
) -> tuple[list[Workspace], int]:
    """Return paginated workspaces under tenant."""

    await _require_tenant(session, tenant_id=tenant_id)
    total = await repo.count_workspaces_page(
        session, tenant_id=tenant_id, name=name, status=status
    )
    offset = (page - 1) * page_size
    rows = await repo.list_workspaces_page(
        session,
        tenant_id=tenant_id,
        name=name,
        status=status,
        offset=offset,
        limit=page_size,
    )
    return rows, total


async def create_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    payload: dict[str, Any],
) -> Workspace:
    """Create workspace under tenant."""

    await _require_tenant(session, tenant_id=tenant_id)
    slug = validate_slug(str(payload["slug"]), code_prefix="workspace")
    row = Workspace(
        tenant_id=tenant_id,
        name=str(payload["name"]).strip(),
        slug=slug,
        status=bool(payload.get("status", True)),
        remark=payload.get("remark"),
    )
    session.add(row)
    await _commit_or_conflict(session, code="workspace.conflict")
    await session.refresh(row)
    return row


async def patch_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
    payload: dict[str, Any],
) -> Workspace:
    """Partially update workspace scoped to tenant."""

    row = await repo.get_workspace_for_tenant(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    if row is None:
        raise AppError("workspace.not_found", "Workspace not found", 404)
    if "name" in payload and payload["name"] is not None:
        row.name = str(payload["name"]).strip()
    if "slug" in payload and payload["slug"] is not None:
        row.slug = validate_slug(str(payload["slug"]), code_prefix="workspace")
    if "status" in payload and payload["status"] is not None:
        row.status = bool(payload["status"])
    if "remark" in payload:
        row.remark = payload["remark"]
    row.update_at = _utc_now()
    await _commit_or_conflict(session, code="workspace.conflict")
    await session.refresh(row)
    return row


async def delete_workspace(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Delete only the workspace row."""

    affected = await repo.delete_workspace_row(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    if affected == 0:
        raise AppError("workspace.not_found", "Workspace not found", 404)
    await session.commit()
```

- [ ] **Step 4: 运行 test PASS**

Run: `cd backend && pytest tests/test_tenant_service.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/tenant/service/ backend/tests/test_tenant_service.py
git commit -m "feat(tenant): add tenant service with slug validation"
```

---

### Task 5: API schemas + deps + router

**Files:**
- Create: `backend/app/sys/tenant/api/deps.py`
- Create: `backend/app/sys/tenant/api/schemas.py`
- Create: `backend/app/sys/tenant/api/router.py`
- Create: `backend/app/sys/tenant/api/__init__.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: 实现 `deps.py`**

```python
"""Authorization dependencies for platform tenant management."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_super_admin_user
from app.dependencies import get_db
from app.exceptions import AppError


async def require_super_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow only platform super administrators."""

    if not await is_super_admin_user(session, user_id=user.id):
        raise AppError(
            "auth.forbidden",
            "Only super-admin can manage tenants",
            403,
        )
    return user
```

- [ ] **Step 2: 实现 `schemas.py`**

定义（含 docstring）：

- `SysTenantOut` — `id, name, slug, status, remark, create_at, update_at`
- `SysTenantCreateIn` / `SysTenantPatchIn`
- `SysTenantListPageOut` — `items, total, page, page_size`
- `SysWorkspaceOut` — 含 `tenant_id`
- `SysWorkspaceCreateIn` / `SysWorkspacePatchIn`
- `SysWorkspaceListPageOut`

- [ ] **Step 3: 实现 `router.py`**

```python
router = APIRouter(prefix="/sys/tenants", tags=["tenants"])
```

端点对齐设计文档 §3.2 / §3.3；所有 handler 依赖 `require_super_admin`；分页默认 `DEFAULT_PAGE_SIZE`。

- [ ] **Step 4: 挂载路由**

`backend/app/core/api/router.py`：

```python
from app.sys.tenant.api.router import router as tenants_router
# ...
api.include_router(tenants_router)
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/tenant/api/ backend/app/core/api/router.py
git commit -m "feat(tenant): add /sys/tenants API routes"
```

---

### Task 6: API 集成测试

**Files:**
- Create: `backend/tests/test_tenant_api.py`
- Create: `backend/tests/test_tenant_workspace_api.py`

- [ ] **Step 1: 编写 `test_tenant_api.py`（override deps 模式，对齐 `test_role_api.py`）**

```python
"""Integration tests for /sys/tenants routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.domain.identity.models import User
from app.errors import register_exception_handlers
from app.exceptions import AppError
from app.sys.tenant.api.deps import require_super_admin
from app.sys.tenant.api.router import router as tenants_router

TENANT_ID = uuid.UUID("00000000-0000-4000-8000-0000000000c1")


async def _deny_super_admin() -> User:
    raise AppError("auth.forbidden", "Not super admin", 403)


async def _allow_super_admin() -> User:
    return User(
        id=uuid.uuid4(),
        email="sa@example.com",
        password_hash="x",
        is_super_admin=True,
    )


def _make_app(*, super_admin: bool) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(tenants_router)
    app.dependency_overrides[require_super_admin] = (
        _allow_super_admin if super_admin else _deny_super_admin
    )
    return app


@pytest.fixture
def sa_client() -> Iterator[TestClient]:
    yield TestClient(_make_app(super_admin=True))


@pytest.fixture
def forbidden_client() -> Iterator[TestClient]:
    yield TestClient(_make_app(super_admin=False))


def test_list_forbidden_for_non_super_admin(forbidden_client: TestClient) -> None:
    response = forbidden_client.get("/sys/tenants")
    assert response.status_code == 403
    assert response.json()["code"] == "auth.forbidden"


def test_list_ok(sa_client: TestClient, monkeypatch) -> None:
    monkeypatch.setattr(
        "app.sys.tenant.api.router.svc.list_tenants_page",
        AsyncMock(return_value=([], 0)),
    )
    response = sa_client.get("/sys/tenants")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 0
```

- [ ] **Step 2: 编写 `test_tenant_workspace_api.py`**

至少覆盖：

- `GET /sys/tenants/{id}/workspaces` 非超管 403
- `DELETE .../workspaces/{wid}` monkeypatch `delete_workspace` 被调用

- [ ] **Step 3: 运行测试 PASS**

Run: `cd backend && pytest tests/test_tenant_api.py tests/test_tenant_workspace_api.py -v`  
Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/test_tenant_api.py backend/tests/test_tenant_workspace_api.py
git commit -m "test(tenant): add tenant and workspace API tests"
```

---

### Task 7: 菜单种子

**Files:**
- Create: `backend/sql/patches/2026-06-11-sys-tenant-menu.sql`
- Modify: `backend/sql/seeds/sys_menu_seed.sql`

- [ ] **Step 1: 编写 menu patch**

```sql
INSERT INTO public.sys_menu (
  id, parent_id, menu_name, i18n_key, menu_key, order_num, path, menu_type, icon, visible, status
) VALUES (
  'f3e8a912-4c1d-5b6a-9e7f-2d8c4a1b0e59',
  '2f899ad8-d7d2-5be5-bf63-feeb426c0bb9',
  '租户管理', 'settings.tenants', 'settings-tenants', 9,
  '/app/settings/tenants', 'C', 'BankOutlined', true, true
) ON CONFLICT (id) DO NOTHING;

UPDATE public.sys_menu
SET order_num = 10
WHERE id = '5a769206-f9bf-5ddd-b4f4-956d40dbc3c9';
```

- [ ] **Step 2: 更新 `sys_menu_seed.sql`**

在角色管理行后插入租户管理（order_num=9）；数据字典改为 order_num=10。

- [ ] **Step 3: Commit**

```bash
git add backend/sql/patches/2026-06-11-sys-tenant-menu.sql backend/sql/seeds/sys_menu_seed.sql
git commit -m "feat(tenant): add settings menu seed for tenant management"
```

---

### Task 8: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/tenants.ts`

- [ ] **Step 1: 实现 API 客户端**

对齐 `frontend/src/api/roles.ts` 模式，导出：

```typescript
export type SysTenantListItem = {
  id: string
  name: string
  slug: string
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type SysTenantListPage = {
  items: SysTenantListItem[]
  total: number
  page: number
  page_size: number
}

export type SysWorkspaceListItem = SysTenantListItem & { tenant_id: string }

// listTenants, createTenant, patchTenant, deleteTenant
// listWorkspaces, createWorkspace, patchWorkspace, deleteWorkspace
```

路径前缀 `/sys/tenants`；workspace 嵌套 `/sys/tenants/${tenantId}/workspaces`。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/tenants.ts
git commit -m "feat(tenant): add frontend tenants API client"
```

---

### Task 9: TenantsPage + TenantFormDrawer

**Files:**
- Create: `frontend/src/features/settings/tenants/TenantsPage.tsx`
- Create: `frontend/src/features/settings/tenants/TenantsPage.css`
- Create: `frontend/src/features/settings/tenants/TenantFormDrawer.tsx`
- Create: `frontend/src/features/settings/tenants/index.ts`
- Modify: `frontend/src/app/router.tsx`
- Modify: `frontend/src/app/layout/AppBreadcrumb.tsx`

- [ ] **Step 1: 实现 `TenantsPage.tsx`**

对齐 `RolesPage.tsx`：

- 筛选：name + status（`allowClear`）
- 表格列：name, slug, status Tag, create_at, update_at, 操作
- 操作：Edit / Popconfirm Delete / ApartmentOutlined → 打开 WorkspaceDrawer
- 顶栏「新增租户」
- `auth.forbidden` → `Result 403`
- 分页 `DEFAULT_PAGE_SIZE`

- [ ] **Step 2: 实现 `TenantFormDrawer.tsx`**

字段：name, slug, status Radio, remark TextArea；全部 Input/Select `allowClear`。

- [ ] **Step 3: 注册路由与 breadcrumb**

`router.tsx`：`{ path: 'tenants', element: <TenantsPage /> }`  
`AppBreadcrumb.tsx`：`pathname.startsWith('/app/settings/tenants')`

- [ ] **Step 4: Commit**

```bash
git add frontend/src/features/settings/tenants/ frontend/src/app/router.tsx frontend/src/app/layout/AppBreadcrumb.tsx
git commit -m "feat(tenant): add TenantsPage and tenant form drawer"
```

---

### Task 10: WorkspaceDrawer + i18n

**Files:**
- Create: `frontend/src/features/settings/tenants/WorkspaceDrawer.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 实现 `WorkspaceDrawer.tsx`**

- 宽度 `720px`
- 外层 Drawer body 包裹 `className="minerva-scrollbar-thin"`，设置 `maxHeight` + `overflowY: 'auto'`
- 内嵌筛选 + Table + 新增按钮
- 内层 Drawer 编辑/创建 workspace
- 删除 Popconfirm 文案说明仅删工作空间记录

- [ ] **Step 2: 添加 i18n 键**

zh-CN 示例：

```json
"settings.tenants": "租户管理",
"tenants.tenantName": "租户名称",
"tenants.slug": "标识",
"tenants.status": "状态",
"tenants.statusNormal": "正常",
"tenants.statusDisabled": "停用",
"tenants.statusAll": "全部",
"tenants.remark": "备注",
"tenants.createAt": "创建时间",
"tenants.updateAt": "修改时间",
"tenants.actions": "操作",
"tenants.addTenant": "新增租户",
"tenants.editTenant": "编辑租户",
"tenants.deleteTenantTitle": "确定删除租户「{{name}}」吗？",
"tenants.deleteTenantDesc": "将同时删除该租户下的成员、工作空间及工作空间成员，不可恢复。",
"tenants.workspaces": "工作空间",
"tenants.addWorkspace": "新增工作空间",
"tenants.deleteWorkspaceTitle": "确定删除工作空间「{{name}}」吗？",
"tenants.deleteWorkspaceDesc": "仅删除工作空间记录，成员与业务数据不会自动清理。",
"tenants.forbidden": "仅平台超级管理员可访问租户管理。",
"tenants.workspaceName": "工作空间名称"
```

en.json 对应英文。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/settings/tenants/WorkspaceDrawer.tsx frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "feat(tenant): add workspace drawer and i18n strings"
```

---

### Task 11: 端到端验证

**Files:** （无新文件）

- [ ] **Step 1: 后端全量测试**

Run: `cd backend && pytest tests/test_tenant_service.py tests/test_tenant_api.py tests/test_tenant_workspace_api.py -v`  
Expected: all PASS

- [ ] **Step 2: 前端类型检查（若项目有 script）**

Run: `cd frontend && npm run build`  
Expected: build succeeds

- [ ] **Step 3: 手动冒烟（超管账号）**

1. 执行 SQL patch：`psql -f backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql` 与 menu patch  
2. 登录超管 → 设置 → 租户管理  
3. 新增租户 → 打开工作空间 Drawer → 新增/编辑/删除工作空间  
4. 非超管账号访问应 403

- [ ] **Step 4: 回填设计文档状态**

修改 `docs/superpowers/specs/2026-06-11-tenant-management-design.md` 头部 **状态** 为「已实现（YYYY-MM-DD）」。

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/specs/2026-06-11-tenant-management-design.md
git commit -m "docs(tenant): mark tenant management spec as implemented"
```

---

## Plan Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| sys_tenants / sys_workspaces 扩展字段 | Task 1–2 |
| require_super_admin 鉴权 | Task 5–6 |
| 租户 CRUD + 级联删除 | Task 3–5 |
| 工作空间嵌套 CRUD + 仅删行 | Task 3–5 |
| 菜单种子 order_num | Task 7 |
| TenantsPage + Drawer UI | Task 9–10 |
| Popconfirm / allowClear / scrollbar | Task 9–10 |
| 测试 | Task 4, 6, 11 |

无 TBD / TODO 占位；类型名 `SysTenantOut` / `SysWorkspaceOut` 与 router schemas 一致。
