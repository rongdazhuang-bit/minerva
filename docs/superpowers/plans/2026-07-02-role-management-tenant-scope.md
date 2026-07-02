# 角色管理租户域 API 与授权优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将角色管理 API 迁移至租户域（`/sys/tenants/{tid}/roles` + 超管 `GET /sys/roles`），并在列表/新建/编辑 UI 中按超管与租户管理员权限提供租户 → 工作空间 scope 选择与筛选。

**Architecture:** 后端在 `role/infrastructure/repository.py` 增加 tenant/platform 分页查询（JOIN 租户/工作空间名称）；`role_service` 提供 `create_role_for_tenant`、`get_role_capabilities`；`deps.py` 新增 `require_tenant_role_manager(tenant_id)` 与 `require_tenant_role_viewer(tenant_id)`；`router.py` 拆为 `platform_router`（`/sys/roles`）与 `tenant_router`（`/sys/tenants/{tenant_id}/roles`）。前端 `RolesPage` 基于 capabilities 渲染 scope 筛选；`RoleFormDrawer` 新建级联、编辑只读 scope。

**Tech Stack:** FastAPI, SQLAlchemy AsyncSession, PostgreSQL, pytest, React 18, Ant Design, TypeScript, react-i18next, @tanstack/react-query。

**设计文档：** `docs/superpowers/specs/2026-07-02-role-management-tenant-scope-design.md`

---

## File Structure

### Backend（修改）

| 文件 | 变更 |
|------|------|
| `backend/app/sys/role/infrastructure/repository.py` | 租户/platform 分页列表；`validate_workspace_in_tenant` |
| `backend/app/sys/role/service/role_service.py` | tenant 域 CRUD；capabilities |
| `backend/app/sys/role/api/deps.py` | `require_tenant_role_manager` / `require_tenant_role_viewer` / `require_super_admin` |
| `backend/app/sys/role/api/schemas.py` | `workspace_id` on create；list 增 `tenant_name`/`workspace_name`；`SysRoleCapabilitiesOut` |
| `backend/app/sys/role/api/router.py` | 重写为 platform + tenant 双 router |
| `backend/app/core/api/router.py` | `include_router(platform_roles_router)` + `include_router(tenant_roles_router)` |
| `backend/app/sys/tenant/api/router.py` | `list_workspaces` 鉴权改为 `require_tenant_admin` |
| `backend/tests/conftest.py` | **新建** 最小 pytest 配置（若不存在） |
| `backend/tests/test_role_service.py` | **新建** service 单元测试 |
| `backend/tests/test_role_api.py` | **新建** 路由鉴权测试 |

### Frontend（修改）

| 文件 | 变更 |
|------|------|
| `frontend/src/api/roles.ts` | 租户域 API 客户端与类型 |
| `frontend/src/features/settings/roles/RolesPage.tsx` | scope 筛选、表格列、CRUD 路径 |
| `frontend/src/features/settings/roles/RoleFormDrawer.tsx` | 新建级联 / 编辑只读 scope |
| `frontend/src/i18n/locales/zh-CN.json` | `roles.tenant` 等 |
| `frontend/src/i18n/locales/en.json` | 同上 |

### Docs（修改）

| 文件 | 变更 |
|------|------|
| `docs/superpowers/specs/2026-07-02-role-management-tenant-scope-design.md` | 状态 → 已实现；§7 实现对照回填 |

---

## Task 1: Repository — 租户/platform 分页查询

**Files:**
- Modify: `backend/app/sys/role/infrastructure/repository.py`
- Test: `backend/tests/test_role_service.py`

- [ ] **Step 1: 编写失败测试 — workspace 归属校验**

创建 `backend/tests/test_role_service.py`：

```python
"""Unit tests for role service helpers."""

from __future__ import annotations

import uuid

import pytest

from app.sys.role.infrastructure import repository as repo


@pytest.mark.asyncio
async def test_validate_workspace_in_tenant_raises_when_mismatch(db_session) -> None:
    """Workspace must belong to the path tenant."""

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    workspace_id = uuid.uuid4()
    # db_session fixture 在 conftest 中插入 Workspace(tenant_id=tenant_a)
    # 此处用 mock 或 skip：若尚无 conftest，先测纯函数分支

    with pytest.raises(Exception):
        await repo.validate_workspace_in_tenant(
            db_session,
            tenant_id=tenant_b,
            workspace_id=workspace_id,
        )
```

若项目尚无 `db_session` fixture，在 `backend/tests/conftest.py` 添加最小 stub：

```python
import pytest
from unittest.mock import AsyncMock


@pytest.fixture
def db_session() -> AsyncMock:
    """Minimal async session stub until full DB fixtures exist."""

    return AsyncMock()
```

并在 Step 3 实现可测的纯 SQL 查询前先实现 `validate_workspace_in_tenant` 使用 `session.get(Workspace, workspace_id)`。

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend
pytest tests/test_role_service.py -v
```

Expected: FAIL — `validate_workspace_in_tenant` 不存在

- [ ] **Step 3: 在 repository.py 追加查询与校验**

在 `backend/app/sys/role/infrastructure/repository.py` 文件顶部 import 补充：

```python
from dataclasses import dataclass
from app.core.domain.identity.models import Tenant, Workspace
```

在文件末尾追加：

```python
@dataclass(frozen=True)
class RoleListRow:
    """Role ORM row plus display names for list API."""

    role: SysRole
    tenant_name: str
    workspace_name: str


def _roles_scoped_base_stmt(
    *,
    tenant_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
):
    """Base SELECT for tenant/platform role lists (workspace-bound roles only)."""

    stmt = (
        select(SysRole, Tenant.name, Workspace.name)
        .join(Tenant, Tenant.id == SysRole.tenant_id)
        .join(Workspace, Workspace.id == SysRole.workspace_id)
        .where(SysRole.workspace_id.is_not(None))
    )
    if tenant_id is not None:
        stmt = stmt.where(SysRole.tenant_id == tenant_id)
    if workspace_id is not None:
        stmt = stmt.where(SysRole.workspace_id == workspace_id)
    return stmt


async def validate_workspace_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> None:
    """Raise role.workspace_invalid when workspace missing or wrong tenant."""

    from app.exceptions import AppError

    ws = await session.get(Workspace, workspace_id)
    if ws is None or ws.tenant_id != tenant_id:
        raise AppError("role.workspace_invalid", "Workspace not found", 400)


async def count_roles_scoped(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> int:
    """Count workspace-bound roles for platform or tenant scope."""

    stmt = select(func.count()).select_from(
        _roles_scoped_base_stmt(tenant_id=tenant_id, workspace_id=workspace_id).subquery()
    )
    # 简化：直接用 base stmt 改 select count
    base = _roles_scoped_base_stmt(tenant_id=tenant_id, workspace_id=workspace_id)
    count_stmt = select(func.count()).select_from(base.subquery())
    if role_name:
        count_stmt = count_stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    # 注意：subquery 过滤应在 base 层完成 — 实现时在 base 上叠加 filter 后 count
    result = await session.execute(
        select(func.count()).select_from(
            _roles_scoped_base_stmt(tenant_id=tenant_id, workspace_id=workspace_id).alias("sq")
        )
    )
    return int(result.scalar_one() or 0)


async def list_roles_scoped_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None = None,
    workspace_id: uuid.UUID | None = None,
    limit: int,
    offset: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> Sequence[RoleListRow]:
    """Return one page of scoped roles with tenant/workspace names."""

    stmt = _roles_scoped_base_stmt(tenant_id=tenant_id, workspace_id=workspace_id)
    if role_name:
        stmt = stmt.where(SysRole.role_name.ilike(f"%{role_name.strip()}%"))
    if status is not None:
        stmt = stmt.where(SysRole.status == status)
    if role_key:
        stmt = stmt.where(SysRole.role_key == role_key.strip())
    stmt = stmt.order_by(*_role_list_order()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return [
        RoleListRow(role=row, tenant_name=t_name, workspace_name=ws_name)
        for row, t_name, ws_name in result.all()
    ]
```

实现 `count_roles_scoped` 时与 `list_roles_scoped_page` 共用同一 filter 构建函数，避免 subquery 错误（实现者提取 `_apply_role_list_filters(stmt, ...)` 私有函数）。

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/role/infrastructure/repository.py backend/tests/
git commit -m "feat(role): add tenant-scoped role list repository queries"
```

---

## Task 2: Service — tenant 域 CRUD 与 capabilities

**Files:**
- Modify: `backend/app/sys/role/service/role_service.py`
- Test: `backend/tests/test_role_service.py`

- [ ] **Step 1: 编写失败测试 — capabilities 纯逻辑**

在 `test_role_service.py` 追加：

```python
from app.sys.role.service import role_service as svc


def test_build_role_capabilities_super_admin() -> None:
    """Super admin can pick tenant and workspace; defaults are all/null."""

    out = svc.build_role_capabilities(
        is_super_admin=True,
        is_tenant_admin=False,
        jwt_tenant_id=None,
        jwt_tenant_name=None,
    )
    assert out["can_pick_tenant"] is True
    assert out["can_pick_workspace"] is True
    assert out["default_filter_tenant_id"] is None
    assert out["default_filter_workspace_id"] is None


def test_build_role_capabilities_tenant_admin() -> None:
    """Tenant admin has fixed tenant and all-workspace default filter."""

    tid = uuid.uuid4()
    out = svc.build_role_capabilities(
        is_super_admin=False,
        is_tenant_admin=True,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
    )
    assert out["can_pick_tenant"] is False
    assert out["fixed_tenant_id"] == tid
    assert out["default_filter_tenant_id"] == tid
    assert out["default_filter_workspace_id"] is None
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd backend
pytest tests/test_role_service.py::test_build_role_capabilities_super_admin -v
```

Expected: FAIL — `build_role_capabilities` 不存在

- [ ] **Step 3: 在 role_service.py 实现**

在 `role_service.py` 追加（保留现有 `create_role` 供过渡，或内联替换）：

```python
def build_role_capabilities(
    *,
    is_super_admin: bool,
    is_tenant_admin: bool,
    jwt_tenant_id: uuid.UUID | None,
    jwt_tenant_name: str | None,
) -> dict[str, object]:
    """Build role form/list capability flags for the current actor."""

    can_pick_tenant = is_super_admin
    can_pick_workspace = is_super_admin or is_tenant_admin
    fixed_tenant_id = None if is_super_admin else jwt_tenant_id
    fixed_tenant_name = None if is_super_admin else jwt_tenant_name
    default_filter_tenant_id = None if is_super_admin else jwt_tenant_id
    default_filter_workspace_id = None
    return {
        "is_super_admin": is_super_admin,
        "is_tenant_admin": is_tenant_admin,
        "can_pick_tenant": can_pick_tenant,
        "can_pick_workspace": can_pick_workspace,
        "fixed_tenant_id": fixed_tenant_id,
        "fixed_tenant_name": fixed_tenant_name,
        "default_filter_tenant_id": default_filter_tenant_id,
        "default_filter_workspace_id": default_filter_workspace_id,
    }


async def get_role_capabilities(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    is_super_admin: bool,
    jwt_tenant_id: uuid.UUID | None,
) -> dict[str, object]:
    """Resolve capabilities using JWT tenant and grant checks."""

    from app.core.domain.authorization.repository import is_tenant_admin
    from app.core.domain.identity.models import Tenant

    is_ta = False
    tenant_name = None
    if jwt_tenant_id is not None:
        is_ta = await is_tenant_admin(
            session, user_id=user_id, tenant_id=jwt_tenant_id
        )
        tenant = await session.get(Tenant, jwt_tenant_id)
        tenant_name = tenant.name if tenant else None
    return build_role_capabilities(
        is_super_admin=is_super_admin,
        is_tenant_admin=is_ta,
        jwt_tenant_id=jwt_tenant_id,
        jwt_tenant_name=tenant_name,
    )


async def list_roles_scoped_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
    page: int,
    page_size: int,
    role_name: str | None = None,
    status: bool | None = None,
    role_key: str | None = None,
) -> tuple[list[repo.RoleListRow], int]:
    """Paginate roles for platform or tenant scope."""

    total = await repo.count_roles_scoped(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    offset = (page - 1) * page_size
    rows = await repo.list_roles_scoped_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return list(rows), total


async def create_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    data: dict[str, Any],
) -> SysRole:
    """Create a workspace-bound role under a tenant path."""

    workspace_id = uuid.UUID(str(data["workspace_id"]))
    await repo.validate_workspace_in_tenant(
        session, tenant_id=tenant_id, workspace_id=workspace_id
    )
    menu_ids: list[uuid.UUID] = list(data.get("menu_ids") or [])
    await _validate_menu_ids(session, menu_ids)
    now = _utc_now()
    row = SysRole(
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        role_name=str(data["role_name"]).strip(),
        role_key=str(data["role_key"]).strip(),
        role_sort=int(data.get("role_sort") or 0),
        status=bool(data.get("status", True)),
        remark=data.get("remark"),
        create_at=now,
        update_at=now,
    )
    await repo.add_role(session, row)
    if menu_ids:
        await repo.replace_role_menus(session, role_id=row.id, menu_ids=menu_ids)
    await _commit_or_conflict(session)
    await session.refresh(row)
    return row


async def get_role_detail_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
) -> tuple[SysRole, list[uuid.UUID], str, str]:
    """Return role, menu ids, tenant name, workspace name."""

    from app.core.domain.identity.models import Tenant, Workspace

    row = await repo.get_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    if row is None or row.workspace_id is None:
        raise AppError("role.not_found", "Role not found", 404)
    menu_ids = await repo.list_menu_ids_for_role(session, role_id)
    tenant = await session.get(Tenant, tenant_id)
    ws = await session.get(Workspace, row.workspace_id)
    return (
        row,
        menu_ids,
        tenant.name if tenant else "",
        ws.name if ws else "",
    )


async def update_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysRole:
    """Patch role fields; ignore tenant_id/workspace_id in patch."""

    patch.pop("workspace_id", None)
    patch.pop("tenant_id", None)
    row = await repo.get_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    if row is None:
        raise AppError("role.not_found", "Role not found", 404)
    return await update_role(
        session,
        workspace_id=row.workspace_id,
        role_id=role_id,
        patch=patch,
    )


async def delete_role_for_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
) -> None:
    """Delete role scoped by tenant path."""

    row = await repo.get_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    if row is None or row.workspace_id is None:
        raise AppError("role.not_found", "Role not found", 404)
    await delete_role(session, workspace_id=row.workspace_id, role_id=role_id)
```

- [ ] **Step 4: 运行 capabilities 测试**

```bash
pytest tests/test_role_service.py::test_build_role_capabilities_super_admin tests/test_role_service.py::test_build_role_capabilities_tenant_admin -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/role/service/role_service.py backend/tests/test_role_service.py
git commit -m "feat(role): add tenant-scoped service and capabilities builder"
```

---

## Task 3: API deps — 租户域鉴权

**Files:**
- Modify: `backend/app/sys/role/api/deps.py`

- [ ] **Step 1: 替换 workspace 版 manager 为 tenant 版**

将 `deps.py` 重写为：

```python
"""Route-level dependencies for tenant-scoped role management."""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.authorization.repository import is_tenant_admin
from app.core.domain.identity.models import User, Workspace
from app.core.domain.identity.services import find_workspace_role_for_user
from app.core.security.permission_resolver import build_permission_context, parse_uuid_claim
from app.dependencies import get_db
from app.exceptions import AppError
from app.sys.tenant.api.deps import require_super_admin


async def require_tenant_role_manager(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow super admin or tenant admin to mutate roles in one tenant."""

    if user.is_super_admin:
        return tenant_id
    if await is_tenant_admin(session, user_id=user.id, tenant_id=tenant_id):
        return tenant_id
    raise AppError("auth.forbidden", "Tenant role manager required", 403)


async def require_tenant_role_viewer(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred=Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow super admin, tenant admin, or workspace member under tenant to read roles."""

    if user.is_super_admin:
        return tenant_id
    if await is_tenant_admin(session, user_id=user.id, tenant_id=tenant_id):
        return tenant_id
    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    wid = parse_uuid_claim(payload, "wid")
    if wid is None:
        raise AppError("auth.forbidden", "Workspace membership required", 403)
    ws = await session.get(Workspace, wid)
    if ws is None or ws.tenant_id != tenant_id:
        raise AppError("auth.forbidden", "Wrong tenant context", 403)
    if await find_workspace_role_for_user(session, user_id=user.id, workspace_id=wid):
        return tenant_id
    raise AppError("auth.forbidden", "Workspace membership required", 403)
```

保留 `require_super_admin` 从 `app.sys.tenant.api.deps` re-export 供 platform list 使用。

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/role/api/deps.py
git commit -m "feat(role): add tenant-scoped role authorization deps"
```

---

## Task 4: Schemas — 请求/响应扩展

**Files:**
- Modify: `backend/app/sys/role/api/schemas.py`

- [ ] **Step 1: 更新 schemas.py**

```python
class SysRoleCreateIn(BaseModel):
    workspace_id: uuid.UUID
    role_name: str = Field(min_length=1, max_length=64)
    role_key: str = Field(min_length=1, max_length=64)
    role_sort: int = 0
    status: bool = True
    remark: str | None = Field(default=None, max_length=500)
    menu_ids: list[uuid.UUID] = Field(default_factory=list)


class SysRoleListItemOut(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str
    workspace_id: uuid.UUID
    workspace_name: str
    role_name: str
    role_key: str
    role_sort: int
    status: bool
    remark: str | None
    create_at: datetime | None = None
    update_at: datetime | None = None


class SysRoleCapabilitiesOut(BaseModel):
    is_super_admin: bool
    is_tenant_admin: bool
    can_pick_tenant: bool
    can_pick_workspace: bool
    fixed_tenant_id: uuid.UUID | None = None
    fixed_tenant_name: str | None = None
    default_filter_tenant_id: uuid.UUID | None = None
    default_filter_workspace_id: uuid.UUID | None = None
```

`SysRoleDetailOut` 继承 `SysRoleListItemOut` 并保留 `menu_ids`。

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/role/api/schemas.py
git commit -m "feat(role): extend schemas for tenant-scoped roles"
```

---

## Task 5: Router — 租户域 + 平台双路由

**Files:**
- Modify: `backend/app/sys/role/api/router.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: 重写 router.py**

```python
"""Tenant-scoped and platform role CRUD routes."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.identity.models import User
from app.core.security.permission_resolver import parse_uuid_claim
from app.dependencies import get_db
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.role.api.deps import (
    require_super_admin,
    require_tenant_role_manager,
    require_tenant_role_viewer,
)
from app.sys.role.api.schemas import (
    SysRoleCapabilitiesOut,
    SysRoleCreateIn,
    SysRoleDetailOut,
    SysRoleListItemOut,
    SysRoleListPageOut,
    SysRolePatchIn,
)
from app.sys.role.infrastructure.repository import RoleListRow
from app.sys.role.service import role_service as svc

platform_router = APIRouter(prefix="/sys/roles", tags=["roles"])
tenant_router = APIRouter(prefix="/sys/tenants/{tenant_id}/roles", tags=["roles"])


def _row_to_list_item(row: RoleListRow) -> SysRoleListItemOut:
    r = row.role
    return SysRoleListItemOut(
        id=r.id,
        tenant_id=r.tenant_id,
        tenant_name=row.tenant_name,
        workspace_id=r.workspace_id,
        workspace_name=row.workspace_name,
        role_name=r.role_name,
        role_key=r.role_key,
        role_sort=r.role_sort,
        status=r.status,
        remark=r.remark,
        create_at=r.create_at,
        update_at=r.update_at,
    )


@platform_router.get("/meta/capabilities", response_model=SysRoleCapabilitiesOut)
async def get_role_capabilities(
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> SysRoleCapabilitiesOut:
    tid = None
    if cred is not None:
        payload = _decode_access_payload(cred)
        tid = parse_uuid_claim(payload, "tid")
    data = await svc.get_role_capabilities(
        session,
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        jwt_tenant_id=tid,
    )
    return SysRoleCapabilitiesOut.model_validate(data)


@platform_router.get("/menu-tree", response_model=list[SysMenuNodeOut])
async def list_role_menu_tree(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> list[SysMenuNodeOut]:
    return await svc.list_menu_tree_for_role_assignment(session)


@platform_router.get("", response_model=SysRoleListPageOut)
async def list_roles_platform(
    tenant_id: uuid.UUID | None = Query(default=None),
    workspace_id: uuid.UUID | None = Query(default=None),
    role_name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    role_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_super_admin),
) -> SysRoleListPageOut:
    rows, total = await svc.list_roles_scoped_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return SysRoleListPageOut(
        items=[_row_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@tenant_router.get("", response_model=SysRoleListPageOut)
async def list_roles_for_tenant(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None),
    role_name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    role_key: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    session: AsyncSession = Depends(get_db),
    _viewer: uuid.UUID = Depends(require_tenant_role_viewer),
) -> SysRoleListPageOut:
    rows, total = await svc.list_roles_scoped_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        role_name=role_name,
        status=status,
        role_key=role_key,
    )
    return SysRoleListPageOut(
        items=[_row_to_list_item(r) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


@tenant_router.post("", response_model=SysRoleDetailOut, status_code=201)
async def create_role(
    tenant_id: uuid.UUID,
    body: SysRoleCreateIn,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> SysRoleDetailOut:
    row = await svc.create_role_for_tenant(
        session, tenant_id=tenant_id, data=body.model_dump()
    )
    detail_row, menu_ids, t_name, ws_name = await svc.get_role_detail_for_tenant(
        session, tenant_id=tenant_id, role_id=row.id
    )
    base = _row_to_list_item(
        RoleListRow(role=detail_row, tenant_name=t_name, workspace_name=ws_name)
    )
    return SysRoleDetailOut(**base.model_dump(), menu_ids=menu_ids)


@tenant_router.get("/{role_id}", response_model=SysRoleDetailOut)
async def get_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _viewer: uuid.UUID = Depends(require_tenant_role_viewer),
) -> SysRoleDetailOut:
    row, menu_ids, t_name, ws_name = await svc.get_role_detail_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    base = _row_to_list_item(
        RoleListRow(role=row, tenant_name=t_name, workspace_name=ws_name)
    )
    return SysRoleDetailOut(**base.model_dump(), menu_ids=menu_ids)


@tenant_router.patch("/{role_id}", response_model=SysRoleDetailOut)
async def patch_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    body: SysRolePatchIn,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> SysRoleDetailOut:
    await svc.update_role_for_tenant(
        session,
        tenant_id=tenant_id,
        role_id=role_id,
        patch=body.model_dump(exclude_unset=True),
    )
    row, menu_ids, t_name, ws_name = await svc.get_role_detail_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    base = _row_to_list_item(
        RoleListRow(role=row, tenant_name=t_name, workspace_name=ws_name)
    )
    return SysRoleDetailOut(**base.model_dump(), menu_ids=menu_ids)


@tenant_router.delete("/{role_id}", status_code=204)
async def delete_role(
    tenant_id: uuid.UUID,
    role_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: uuid.UUID = Depends(require_tenant_role_manager),
) -> Response:
    await svc.delete_role_for_tenant(
        session, tenant_id=tenant_id, role_id=role_id
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

删除原 `/workspaces/{workspace_id}/roles` 全部端点。

- [ ] **Step 2: 更新 core/api/router.py**

```python
from app.sys.role.api.router import platform_router as roles_platform_router
from app.sys.role.api.router import tenant_router as roles_tenant_router

api.include_router(roles_platform_router)
api.include_router(roles_tenant_router)
```

移除旧的 `from app.sys.role.api.router import router as roles_router`。

- [ ] **Step 3: 手动冒烟**

```bash
cd backend
uvicorn app.main:app --reload
# 超管: GET /api/sys/roles
# 租户管理员: GET /api/sys/tenants/{tid}/roles
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/role/api/router.py backend/app/core/api/router.py
git commit -m "feat(role): migrate role API to tenant-scoped routes"
```

---

## Task 6: 放宽 workspace 列表鉴权

**Files:**
- Modify: `backend/app/sys/tenant/api/router.py`

- [ ] **Step 1: 修改 list_workspaces 依赖**

在 `list_workspaces` 路由将：

```python
_admin: User = Depends(require_super_admin),
```

改为：

```python
_admin: User = Depends(require_tenant_admin),
```

（`require_tenant_admin` 已支持超管 + 该租户管理员。）

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/tenant/api/router.py
git commit -m "feat(tenant): allow tenant admin to list workspaces for role picker"
```

---

## Task 7: 后端 API 鉴权测试

**Files:**
- Create: `backend/tests/test_role_api.py`

- [ ] **Step 1: 编写集成测试骨架**

```python
"""Role API authorization tests."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_platform_roles_forbidden_for_non_super_admin(auth_headers_member) -> None:
    """Non-super-admin cannot list platform roles."""

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        resp = await client.get("/api/sys/roles", headers=auth_headers_member)
    assert resp.status_code == 403
```

若尚无 `auth_headers_member` fixture，在 `conftest.py` 中按 `test_user_api.py` 模式补充，或先用 `@pytest.mark.skip(reason="needs auth fixtures")` 占位并在实现时启用。

- [ ] **Step 2: Commit**

```bash
git add backend/tests/test_role_api.py
git commit -m "test(role): add platform list authorization test"
```

---

## Task 8: 前端 API 客户端

**Files:**
- Modify: `frontend/src/api/roles.ts`

- [ ] **Step 1: 重写 roles.ts**

```typescript
import { apiJson } from '@/api/client'
import type { SysMenuNode } from '@/api/menus'

export type SysRoleCapabilities = {
  is_super_admin: boolean
  is_tenant_admin: boolean
  can_pick_tenant: boolean
  can_pick_workspace: boolean
  fixed_tenant_id: string | null
  fixed_tenant_name: string | null
  default_filter_tenant_id: string | null
  default_filter_workspace_id: string | null
}

export type SysRoleListItem = {
  id: string
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
  role_name: string
  role_key: string
  role_sort: number
  status: boolean
  remark: string | null
  create_at: string | null
  update_at: string | null
}

export type SysRoleDetail = SysRoleListItem & { menu_ids: string[] }

export type SysRoleListParams = {
  tenant_id?: string
  workspace_id?: string
  role_name?: string
  status?: boolean
  role_key?: string
  page?: number
  page_size?: number
}

export type SysRoleCreateBody = {
  workspace_id: string
  role_name: string
  role_key: string
  role_sort?: number
  status?: boolean
  remark?: string | null
  menu_ids?: string[]
}

function buildQuery(params: SysRoleListParams): string {
  const q = new URLSearchParams()
  if (params.tenant_id) q.set('tenant_id', params.tenant_id)
  if (params.workspace_id) q.set('workspace_id', params.workspace_id)
  if (params.role_name?.trim()) q.set('role_name', params.role_name.trim())
  if (params.status !== undefined) q.set('status', String(params.status))
  if (params.page != null) q.set('page', String(params.page))
  if (params.page_size != null) q.set('page_size', String(params.page_size))
  const s = q.toString()
  return s ? `?${s}` : ''
}

export function getRoleCapabilities() {
  return apiJson<SysRoleCapabilities>('/sys/roles/meta/capabilities')
}

export function listRolesPlatform(params: SysRoleListParams = {}) {
  return apiJson<SysRoleListPage>(`/sys/roles${buildQuery(params)}`)
}

export function listRolesForTenant(tenantId: string, params: SysRoleListParams = {}) {
  return apiJson<SysRoleListPage>(
    `/sys/tenants/${tenantId}/roles${buildQuery(params)}`,
  )
}

export function listRoleMenuTree() {
  return apiJson<SysMenuNode[]>('/sys/roles/menu-tree')
}

export function getRole(tenantId: string, roleId: string) {
  return apiJson<SysRoleDetail>(`/sys/tenants/${tenantId}/roles/${roleId}`)
}

export function createRole(tenantId: string, body: SysRoleCreateBody) {
  return apiJson<SysRoleDetail>(`/sys/tenants/${tenantId}/roles`, {
    method: 'POST',
    body: JSON.stringify(body),
  })
}

export function patchRole(tenantId: string, roleId: string, body: Partial<SysRoleCreateBody>) {
  return apiJson<SysRoleDetail>(`/sys/tenants/${tenantId}/roles/${roleId}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  })
}

export function deleteRole(tenantId: string, roleId: string) {
  return apiJson<void>(`/sys/tenants/${tenantId}/roles/${roleId}`, {
    method: 'DELETE',
  })
}
```

保留 `SysRoleListPage` 类型定义。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/roles.ts
git commit -m "feat(role): update frontend API client for tenant-scoped routes"
```

---

## Task 9: RoleFormDrawer — scope 选择

**Files:**
- Modify: `frontend/src/features/settings/roles/RoleFormDrawer.tsx`

- [ ] **Step 1: 扩展 Props 与表单字段**

在 `RoleFormDrawer` 增加：

```typescript
import { Tag } from 'antd'
import type { SysRoleCapabilities } from '@/api/roles'

type RoleScope = {
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
}

type Props = {
  // ...existing
  mode: 'create' | 'edit'
  capabilities: SysRoleCapabilities | null
  initialScope?: RoleScope | null
  tenants?: { id: string; name: string }[]
  workspaces?: { id: string; name: string }[]
  onTenantChange?: (tenantId: string) => void
  metaLoading?: boolean
}
```

**新建模式**（`mode === 'create'`）：

- `capabilities.can_pick_tenant` → `Form.Item name="tenant_id"` Select
- 否则 → `Tag` 展示 `capabilities.fixed_tenant_name`
- `Form.Item name="workspace_id"` Select，`rules={[{ required: true }]}`

**编辑模式**：顶部只读：

```tsx
{mode === 'edit' && initialScope && (
  <Form.Item label={t('roles.scope')}>
    <span>{initialScope.tenant_name} &gt; {initialScope.workspace_name}</span>
  </Form.Item>
)}
```

`handleFinish` 在 create 时将 `workspace_id` 并入 submit body（由 `RolesPage.onSubmit` 处理 `tenant_id` 路由参数）。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/features/settings/roles/RoleFormDrawer.tsx
git commit -m "feat(role): add tenant/workspace scope to role form drawer"
```

---

## Task 10: RolesPage — scope 筛选与 CRUD

**Files:**
- Modify: `frontend/src/features/settings/roles/RolesPage.tsx`

- [ ] **Step 1: 加载 capabilities 与 scope 状态**

```typescript
const [capabilities, setCapabilities] = useState<SysRoleCapabilities | null>(null)
const [filterTenantId, setFilterTenantId] = useState<string | null>(null)
const [filterWorkspaceId, setFilterWorkspaceId] = useState<string | null>(null)
const [tenants, setTenants] = useState<SysTenantListItem[]>([])
const [workspaces, setWorkspaces] = useState<SysWorkspaceListItem[]>([])

useEffect(() => {
  void getRoleCapabilities().then((caps) => {
    setCapabilities(caps)
    setFilterTenantId(caps.default_filter_tenant_id)
    setFilterWorkspaceId(caps.default_filter_workspace_id)
  })
}, [])
```

超管 mount 后 `listTenants({ page_size: 100 })` 填充租户下拉。

- [ ] **Step 2: 列表 query 分支**

```typescript
const listQuery = useQuery({
  queryKey: ['roles', filterTenantId, filterWorkspaceId, page, pageSize, filters, refreshTick],
  queryFn: async () => {
    const params = { ...filters, page, page_size: pageSize, workspace_id: filterWorkspaceId ?? undefined }
    if (capabilities?.can_pick_tenant && !filterTenantId) {
      return listRolesPlatform({ ...params, tenant_id: undefined })
    }
    const tid = filterTenantId ?? capabilities?.fixed_tenant_id
    if (!tid) throw new Error('tenant required')
    return listRolesForTenant(tid, params)
  },
  enabled: Boolean(capabilities),
})
```

- [ ] **Step 3: 表格增列 tenant_name / workspace_name**

- [ ] **Step 4: openCreate / openEdit / handleSubmit / handleDelete 使用 row.tenant_id**

```typescript
await createRole(selectedTenantId, { workspace_id: selectedWorkspaceId, ...body })
await patchRole(row.tenant_id, row.id, body)
await deleteRole(row.tenant_id, row.id)
await getRole(row.tenant_id, row.id)
```

- [ ] **Step 5: 普通成员无 scope 筛选**

当 `!capabilities?.can_pick_workspace && !capabilities?.can_pick_tenant` 时，用 JWT `tenantId` + `workspaceId` 固定查询。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/settings/roles/RolesPage.tsx
git commit -m "feat(role): add tenant/workspace filters and tenant-scoped CRUD on roles page"
```

---

## Task 11: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 追加文案**

zh-CN：

```json
"roles.tenant": "租户",
"roles.workspace": "工作空间",
"roles.allTenants": "全部租户",
"roles.allWorkspaces": "全部工作空间",
"roles.scope": "归属范围",
"roles.workspaceRequired": "请选择工作空间"
```

en：

```json
"roles.tenant": "Tenant",
"roles.workspace": "Workspace",
"roles.allTenants": "All tenants",
"roles.allWorkspaces": "All workspaces",
"roles.scope": "Scope",
"roles.workspaceRequired": "Please select a workspace"
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "i18n: add role tenant/workspace scope labels"
```

---

## Task 12: 文档回填与 spec 状态

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-role-management-tenant-scope-design.md`

- [ ] **Step 1: 更新 spec 状态与 §7 实现对照**

将文首 `**状态**：待实现` 改为 `**状态**：已实现（2026-07-02）`，§7 各行状态改为「已实现」并填入实际代码路径。

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-07-02-role-management-tenant-scope-design.md
git commit -m "docs: mark role tenant-scope spec as implemented"
```

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| `GET /sys/roles` 超管跨租户 | Task 5 |
| `GET/POST/PATCH/DELETE /sys/tenants/{tid}/roles` | Task 5 |
| `GET /sys/roles/menu-tree` | Task 5 |
| `GET /sys/roles/meta/capabilities` | Task 2, 5 |
| 删除旧 workspace 路由 | Task 5 |
| workspace 列表鉴权放宽 | Task 6 |
| 创建 workspace_id 必填 | Task 2, 4 |
| 编辑 scope 只读 | Task 9, 10 |
| 列表 scope 筛选与默认值 | Task 10 |
| 超管/租户管理员矩阵 | Task 2, 3, 9, 10 |
| i18n | Task 11 |
| 保留 users/meta/roles | 无变更（spec §3.3） |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-role-management-tenant-scope.md`.

**Two execution options:**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间 review，迭代快  
2. **Inline Execution** — 本会话用 executing-plans 按 Task 批量执行，checkpoint Review

**Which approach?**
