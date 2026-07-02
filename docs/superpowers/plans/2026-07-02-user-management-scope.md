# 用户管理租户域 Scope 联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为超管/租户管理员提供租户→工作空间联动的用户列表筛选与新建/编辑表单 scope UI，新增租户级 `workspace-users` 列表 API 与平台 `capabilities` 端点；工作空间管理员保持现网行为。

**Architecture:** 后端在 `user_service` 抽取 `build_user_list_capabilities`（对齐 `role_service.build_role_capabilities`），新增 tenant 域分页查询复用 `_build_list_row`；前端 `UsersPage`/`UserFormDrawer` 对齐 `RolesPage`/`RoleFormDrawer` 双轨列表与 scope 表单模式。写操作仍走 `/workspaces/{wid}/users`。

**Tech Stack:** FastAPI + SQLAlchemy async（后端），React + Ant Design + TanStack Query（前端），pytest（后端单元测试）

**Spec:** [docs/superpowers/specs/2026-07-02-user-management-scope-design.md](../specs/2026-07-02-user-management-scope-design.md)

---

## File Map

| File | Responsibility |
|------|----------------|
| `backend/app/sys/user/service/user_service.py` | `build_user_list_capabilities`、`get_user_list_capabilities`、`list_tenant_workspace_users_page`、enrich `tenant_name`/`workspace_name` |
| `backend/app/sys/user/infrastructure/repository.py` | `count_tenant_workspace_members`、`list_tenant_workspace_members_page` |
| `backend/app/sys/user/api/schemas.py` | 扩展 `SysUserListItemOut`；新增 `SysUserListCapabilitiesOut` |
| `backend/app/sys/user/api/platform_router.py` | **新建** — `GET /sys/users/meta/capabilities` |
| `backend/app/sys/tenant/api/router.py` | 新增 `GET /{tenant_id}/workspace-users` |
| `backend/app/core/api/router.py` | 注册 `users_platform_router` |
| `backend/tests/sys/user/test_user_list_capabilities.py` | **新建** — capabilities 单元测试 |
| `backend/tests/sys/user/test_tenant_workspace_users_repo.py` | **新建** — repository 查询结构测试（可选 mock） |
| `frontend/src/api/users.ts` | 新类型、`getUserListCapabilities`、`listTenantWorkspaceUsers` |
| `frontend/src/features/settings/users/UsersPage.tsx` | scope 筛选、双轨列表、编辑 scope 上下文 |
| `frontend/src/features/settings/users/UserFormDrawer.tsx` | 对齐 RoleFormDrawer scope UI、角色联动 |
| `docs/superpowers/specs/2026-07-02-user-management-scope-design.md` | 实现完成后状态改为「已实现」 |

---

## Task 1: `build_user_list_capabilities` 纯函数 + 测试

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`
- Create: `backend/tests/sys/user/test_user_list_capabilities.py`
- Create: `backend/tests/__init__.py`（若不存在）
- Create: `backend/tests/sys/__init__.py`
- Create: `backend/tests/sys/user/__init__.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/sys/user/test_user_list_capabilities.py
import uuid

from app.sys.user.service.user_service import build_user_list_capabilities


def test_super_admin_can_pick_tenant_and_workspace():
    tid = uuid.uuid4()
    wid = uuid.uuid4()
    caps = build_user_list_capabilities(
        is_super_admin=True,
        is_tenant_admin=False,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
        jwt_workspace_id=wid,
        actor_workspace_role="admin",
        assignable_membership_roles=["admin", "member"],
        can_edit_membership_role=True,
    )
    assert caps["can_pick_tenant"] is True
    assert caps["can_pick_workspace"] is True
    assert caps["fixed_tenant_id"] is None
    assert caps["default_filter_tenant_id"] == tid
    assert caps["default_filter_workspace_id"] == wid


def test_tenant_admin_fixed_tenant_can_pick_workspace():
    tid = uuid.uuid4()
    wid = uuid.uuid4()
    caps = build_user_list_capabilities(
        is_super_admin=False,
        is_tenant_admin=True,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
        jwt_workspace_id=wid,
        actor_workspace_role=None,
        assignable_membership_roles=["admin", "member"],
        can_edit_membership_role=True,
    )
    assert caps["can_pick_tenant"] is False
    assert caps["can_pick_workspace"] is True
    assert caps["fixed_tenant_id"] == tid
    assert caps["fixed_tenant_name"] == "Acme"
    assert caps["default_filter_tenant_id"] == tid
    assert caps["default_filter_workspace_id"] == wid


def test_workspace_admin_no_scope_pickers():
    tid = uuid.uuid4()
    wid = uuid.uuid4()
    caps = build_user_list_capabilities(
        is_super_admin=False,
        is_tenant_admin=False,
        jwt_tenant_id=tid,
        jwt_tenant_name="Acme",
        jwt_workspace_id=wid,
        actor_workspace_role="admin",
        assignable_membership_roles=["admin", "member"],
        can_edit_membership_role=True,
    )
    assert caps["can_pick_tenant"] is False
    assert caps["can_pick_workspace"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/sys/user/test_user_list_capabilities.py -v`

Expected: FAIL — `ImportError: cannot import name 'build_user_list_capabilities'`

- [ ] **Step 3: Implement `build_user_list_capabilities`**

在 `user_service.py` 顶部区域（`get_actor_capabilities` 之前）添加：

```python
def build_user_list_capabilities(
    *,
    is_super_admin: bool,
    is_tenant_admin: bool,
    jwt_tenant_id: uuid.UUID | None,
    jwt_tenant_name: str | None,
    jwt_workspace_id: uuid.UUID | None,
    actor_workspace_role: str | None,
    assignable_membership_roles: list[str],
    can_edit_membership_role: bool,
) -> dict[str, object]:
    """Build list/form scope capability flags (platform-level, JWT-driven)."""

    can_pick_tenant = is_super_admin
    can_pick_workspace = is_super_admin or is_tenant_admin
    fixed_tenant_id = None if is_super_admin else jwt_tenant_id
    fixed_tenant_name = None if is_super_admin else jwt_tenant_name
    return {
        "is_super_admin": is_super_admin,
        "is_tenant_admin": is_tenant_admin,
        "can_pick_tenant": can_pick_tenant,
        "can_pick_workspace": can_pick_workspace,
        "fixed_tenant_id": fixed_tenant_id,
        "fixed_tenant_name": fixed_tenant_name,
        "default_filter_tenant_id": jwt_tenant_id,
        "default_filter_workspace_id": jwt_workspace_id,
        "actor_workspace_role": actor_workspace_role,
        "can_edit_membership_role": can_edit_membership_role,
        "assignable_membership_roles": assignable_membership_roles,
        # backward compat for workspace-scoped meta endpoint
        "can_pick_tenant_workspace": can_pick_tenant,
        "default_tenant_id": jwt_tenant_id if is_super_admin else None,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/sys/user/test_user_list_capabilities.py -v`

Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/user/service/user_service.py backend/tests/
git commit -m "feat(user): add build_user_list_capabilities with unit tests"
```

---

## Task 2: Schema + 平台 capabilities API

**Files:**
- Modify: `backend/app/sys/user/api/schemas.py`
- Create: `backend/app/sys/user/api/platform_router.py`
- Modify: `backend/app/sys/user/service/user_service.py`
- Modify: `backend/app/core/api/router.py`

- [ ] **Step 1: Extend schemas**

在 `schemas.py` 中：

1. `SysUserListItemOut` 增加字段：
```python
tenant_name: str | None = None
workspace_name: str | None = None
```

2. 新增 `SysUserListCapabilitiesOut`：
```python
class SysUserListCapabilitiesOut(BaseModel):
    is_super_admin: bool
    is_tenant_admin: bool
    can_pick_tenant: bool
    can_pick_workspace: bool
    fixed_tenant_id: uuid.UUID | None = None
    fixed_tenant_name: str | None = None
    default_filter_tenant_id: uuid.UUID | None = None
    default_filter_workspace_id: uuid.UUID | None = None
    actor_workspace_role: str | None
    can_edit_membership_role: bool
    assignable_membership_roles: list[str]
```

3. `SysUserCapabilitiesOut` 增加可选字段 `can_pick_tenant`、`can_pick_workspace`（workspace meta 端点复用时填充）。

- [ ] **Step 2: Add `get_user_list_capabilities` service**

```python
async def get_user_list_capabilities(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    is_super_admin: bool,
    jwt_tenant_id: uuid.UUID | None,
    jwt_workspace_id: uuid.UUID | None,
) -> dict[str, object]:
    from app.core.domain.identity.models import Tenant

    is_ta = False
    tenant_name = None
    if jwt_tenant_id is not None:
        is_ta = await auth_repo.is_tenant_admin(
            session, user_id=user_id, tenant_id=jwt_tenant_id
        )
        tenant = await session.get(Tenant, jwt_tenant_id)
        tenant_name = tenant.name if tenant else None

    actor_role = None
    assignable: list[str] = ["member"]
    can_edit = False
    if jwt_workspace_id is not None:
        ws_role = await find_workspace_role_for_user(
            session, user_id=user_id, workspace_id=jwt_workspace_id
        )
        has_membership = ws_role is not None
        assignable = resolve_assignable_membership_roles(
            actor_workspace_role=ws_role,
            actor_is_super_admin=is_super_admin,
            actor_is_tenant_admin=is_ta,
            actor_has_workspace_membership=has_membership,
        )
        can_edit = can_edit_membership_role(
            actor_workspace_role=ws_role,
            actor_is_super_admin=is_super_admin,
            actor_is_tenant_admin=is_ta,
            actor_has_workspace_membership=has_membership,
        )
        actor_role = ws_role.value if ws_role else None

    return build_user_list_capabilities(
        is_super_admin=is_super_admin,
        is_tenant_admin=is_ta,
        jwt_tenant_id=jwt_tenant_id,
        jwt_tenant_name=tenant_name,
        jwt_workspace_id=jwt_workspace_id,
        actor_workspace_role=actor_role,
        assignable_membership_roles=assignable,
        can_edit_membership_role=can_edit,
    )
```

- [ ] **Step 3: Create platform router**

```python
# backend/app/sys/user/api/platform_router.py
"""Platform-level routes for user list scope and capabilities."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.identity.models import User
from app.core.security.permission_resolver import parse_uuid_claim
from app.dependencies import get_db
from app.sys.user.api.schemas import SysUserListCapabilitiesOut
from app.sys.user.service import user_service as svc

router = APIRouter(prefix="/sys/users", tags=["users"])


@router.get("/meta/capabilities", response_model=SysUserListCapabilitiesOut)
async def get_user_list_capabilities(
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> SysUserListCapabilitiesOut:
    """Return user list/form scope capability flags from JWT context."""

    tid: uuid.UUID | None = None
    wid: uuid.UUID | None = None
    if cred is not None:
        payload = _decode_access_payload(cred)
        tid = parse_uuid_claim(payload, "tid")
        wid = parse_uuid_claim(payload, "wid")
    data = await svc.get_user_list_capabilities(
        session,
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        jwt_tenant_id=tid,
        jwt_workspace_id=wid,
    )
    return SysUserListCapabilitiesOut.model_validate(data)
```

- [ ] **Step 4: Register router in `core/api/router.py`**

```python
from app.sys.user.api.platform_router import router as users_platform_router
# ...
api.include_router(users_platform_router)
```

放在 `users_router` 之前或之后均可。

- [ ] **Step 5: Manual smoke test**

启动后端，以超管 token 调用：

```bash
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/sys/users/meta/capabilities
```

Expected: JSON 含 `can_pick_tenant: true`、`default_filter_workspace_id` 为 JWT wid。

- [ ] **Step 6: Commit**

```bash
git add backend/app/sys/user/api/schemas.py backend/app/sys/user/api/platform_router.py \
  backend/app/sys/user/service/user_service.py backend/app/core/api/router.py
git commit -m "feat(user): add platform GET /sys/users/meta/capabilities"
```

---

## Task 3: Repository — 租户域成员分页查询

**Files:**
- Modify: `backend/app/sys/user/infrastructure/repository.py`

- [ ] **Step 1: Add tenant-scoped filter helper**

在 `_apply_member_filters` 之后新增 `_apply_tenant_member_filters`：

```python
def _apply_tenant_member_filters(
    stmt,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    email: str | None,
    nickname: str | None,
    phone: str | None,
    status: bool | None,
    membership_role: MembershipRole | None,
    role_id: uuid.UUID | None,
):
    """Apply list filters for tenant-scoped workspace member queries."""

    stmt = stmt.where(Workspace.tenant_id == tenant_id)
    if workspace_id is not None:
        stmt = stmt.where(WorkspaceMembership.workspace_id == workspace_id)
    if email:
        stmt = stmt.where(User.email.ilike(f"%{email.strip()}%"))
    if nickname:
        stmt = stmt.where(User.nickname.ilike(f"%{nickname.strip()}%"))
    if phone:
        stmt = stmt.where(User.phone.ilike(f"%{phone.strip()}%"))
    if status is not None:
        stmt = stmt.where(User.status == status)
    if membership_role is not None:
        stmt = stmt.where(WorkspaceMembership.role == membership_role)
    if role_id is not None:
        scope_match = (
            SysUserGrant.scope_id == WorkspaceMembership.workspace_id
            if workspace_id is None
            else SysUserGrant.scope_id == workspace_id
        )
        stmt = stmt.where(
            User.id.in_(
                select(SysUserGrant.user_id).where(
                    SysUserGrant.role_id == role_id,
                    SysUserGrant.grant_type == GrantType.role.value,
                    SysUserGrant.scope_type == GrantScopeType.workspace.value,
                    scope_match,
                    SysUserGrant.status.is_(True),
                )
            )
        )
    return stmt
```

- [ ] **Step 2: Add count + page functions**

```python
async def count_tenant_workspace_members(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> int:
    stmt = (
        select(func.count())
        .select_from(User)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
    )
    stmt = _apply_tenant_member_filters(
        stmt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_tenant_workspace_members_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    limit: int,
    offset: int,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> Sequence[tuple[User, WorkspaceMembership, Workspace]]:
    stmt = (
        select(User, WorkspaceMembership, Workspace)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
    )
    stmt = _apply_tenant_member_filters(
        stmt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    stmt = stmt.order_by(*_member_list_order()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.all()
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/sys/user/infrastructure/repository.py
git commit -m "feat(user): add tenant-scoped workspace member repository queries"
```

---

## Task 4: Service + Tenant Router — `workspace-users` 列表 API

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`
- Modify: `backend/app/sys/tenant/api/router.py`

- [ ] **Step 1: Add `list_tenant_workspace_users_page` service**

```python
async def list_tenant_workspace_users_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    page: int,
    page_size: int,
    actor_is_super_admin: bool,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> tuple[list[dict[str, Any]], int]:
    total = await repo.count_tenant_workspace_members(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    offset = max(0, (page - 1) * page_size)
    rows = await repo.list_tenant_workspace_members_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    items: list[dict[str, Any]] = []
    for user, membership, workspace in rows:
        list_row = await _build_list_row(
            session,
            workspace_id=membership.workspace_id,
            user=user,
            membership=membership,
            actor_is_super_admin=actor_is_super_admin,
        )
        payload = row_to_dict(
            list_row,
            workspace_id=membership.workspace_id,
            tenant_id=tenant_id,
        )
        payload["tenant_name"] = workspace.tenant_id  # fix: load tenant name
        payload["workspace_name"] = workspace.name
        # Resolve tenant_name from Tenant ORM (session.get(Tenant, tenant_id))
        tenant = await session.get(Tenant, tenant_id)
        payload["tenant_name"] = tenant.name if tenant else ""
        items.append(payload)
    return items, total
```

（实现时注意 import `Tenant`；`tenant_name` 在循环外查询一次即可。）

- [ ] **Step 2: Add route to tenant router**

```python
from app.sys.tenant.api.deps import require_tenant_admin
from app.sys.user.api.schemas import SysUserListPageOut
from app.sys.user.service import user_service as user_svc

@router.get("/{tenant_id}/workspace-users", response_model=SysUserListPageOut)
async def list_tenant_workspace_users(
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None = Query(default=None),
    email: str | None = Query(default=None),
    nickname: str | None = Query(default=None),
    phone: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    membership_role: str | None = Query(default=None),
    role_id: uuid.UUID | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
    actor: User = Depends(require_tenant_admin),
    session: AsyncSession = Depends(get_db),
) -> SysUserListPageOut:
    await svc.get_tenant(session, tenant_id=tenant_id)
    items, total = await user_svc.list_tenant_workspace_users_page(
        session,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        actor_is_super_admin=actor.is_super_admin,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=_parse_membership_role(membership_role),  # import helper or duplicate
        role_id=role_id,
    )
    return SysUserListPageOut(
        items=[SysUserListItemOut.model_validate(i) for i in items],
        total=total,
        page=page,
        page_size=page_size,
    )
```

将 `_parse_membership_role` 抽到 `app/sys/user/api/common.py` 或在 tenant router 内复制 5 行解析函数，避免循环 import。

- [ ] **Step 3: Smoke test**

```bash
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/sys/tenants/$TENANT_ID/workspace-users?workspace_id=$WID&page=1&page_size=20"
```

Expected: 与 `GET /workspaces/$WID/users` 同 workspace 下结果一致，且含 `tenant_name`、`workspace_name`。

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/user/service/user_service.py backend/app/sys/tenant/api/router.py
git commit -m "feat(user): add GET /sys/tenants/{id}/workspace-users list API"
```

---

## Task 5: Enrich workspace 级列表/详情 `tenant_name` / `workspace_name`

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`

- [ ] **Step 1: Extend `_row_to_response_dict`**

```python
async def _row_to_response_dict(
    session: AsyncSession,
    row: UserListRow,
    *,
    workspace_id: uuid.UUID,
) -> dict[str, Any]:
    from app.core.domain.identity.models import Tenant, Workspace

    tenant_id = await repo.get_tenant_id_for_workspace(
        session, workspace_id=workspace_id
    )
    payload = row_to_dict(row, workspace_id=workspace_id, tenant_id=tenant_id)
    ws = await session.get(Workspace, workspace_id)
    payload["workspace_name"] = ws.name if ws else None
    if tenant_id is not None:
        tenant = await session.get(Tenant, tenant_id)
        payload["tenant_name"] = tenant.name if tenant else None
    return payload
```

- [ ] **Step 2: Smoke test** — `GET /workspaces/{wid}/users/{uid}` 响应含名称字段。

- [ ] **Step 3: Commit**

```bash
git add backend/app/sys/user/service/user_service.py
git commit -m "feat(user): add tenant_name and workspace_name to user list items"
```

---

## Task 6: 前端 API 客户端

**Files:**
- Modify: `frontend/src/api/users.ts`

- [ ] **Step 1: Add types and extend `SysUserListItem`**

```typescript
export type SysUserListCapabilities = {
  is_super_admin: boolean
  is_tenant_admin: boolean
  can_pick_tenant: boolean
  can_pick_workspace: boolean
  fixed_tenant_id: string | null
  fixed_tenant_name: string | null
  default_filter_tenant_id: string | null
  default_filter_workspace_id: string | null
  actor_workspace_role: string | null
  can_edit_membership_role: boolean
  assignable_membership_roles: string[]
}
```

`SysUserListItem` 增加 `tenant_name?: string | null`、`workspace_name?: string | null`。

扩展 `SysUserCapabilities` 增加 `can_pick_tenant?`、`can_pick_workspace?`、`fixed_tenant_id?`、`fixed_tenant_name?`。

- [ ] **Step 2: Extend `buildQuery` 支持 `workspace_id`**

```typescript
export type SysUserListParams = {
  // existing...
  workspace_id?: string
}

function buildQuery(params: SysUserListParams): string {
  // ...
  if (params.workspace_id?.trim()) q.set('workspace_id', params.workspace_id.trim())
}
```

- [ ] **Step 3: Add API functions**

```typescript
export function getUserListCapabilities() {
  return apiJson<SysUserListCapabilities>('/sys/users/meta/capabilities')
}

export function listTenantWorkspaceUsers(
  tenantId: string,
  params: SysUserListParams = {},
) {
  return apiJson<SysUserListPage>(
    `/sys/tenants/${tenantId}/workspace-users${buildQuery(params)}`,
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/users.ts
git commit -m "feat(user): add tenant workspace-users API client"
```

---

## Task 7: `UsersPage` scope 筛选与双轨列表

**Files:**
- Modify: `frontend/src/features/settings/users/UsersPage.tsx`
- Modify: `frontend/src/features/settings/users/UsersPage.css`（如需，复用 roles 页 header 布局类名或复制 scope 样式）

**参考：** `frontend/src/features/settings/roles/RolesPage.tsx` 第 80–188、357–506 行。

- [ ] **Step 1: Add state and capabilities bootstrap**

```typescript
import { getUserListCapabilities, listTenantWorkspaceUsers, type SysUserListCapabilities } from '@/api/users'
import { listTenants, listWorkspaces, type SysTenantListItem, type SysWorkspaceListItem } from '@/api/tenants'

// state
const [capabilities, setCapabilities] = useState<SysUserListCapabilities | null>(null)
const [filterTenantId, setFilterTenantId] = useState<string | null>(null)
const [filterWorkspaceId, setFilterWorkspaceId] = useState<string | null>(null)
const [tenants, setTenants] = useState<SysTenantListItem[]>([])
const [filterWorkspaces, setFilterWorkspaces] = useState<SysWorkspaceListItem[]>([])

useEffect(() => {
  void getUserListCapabilities().then((caps) => {
    setCapabilities(caps)
    setFilterTenantId(caps.default_filter_tenant_id)
    setFilterWorkspaceId(caps.default_filter_workspace_id)
  })
}, [])
```

- [ ] **Step 2: Add effective scope + dual list query**

```typescript
const effectiveTenantId = useMemo(() => {
  if (!capabilities) return null
  if (capabilities.can_pick_tenant) return filterTenantId
  return capabilities.fixed_tenant_id ?? tenantId
}, [capabilities, filterTenantId, tenantId])

const effectiveWorkspaceId = useMemo(() => {
  if (!capabilities) return null
  if (capabilities.can_pick_workspace) return filterWorkspaceId
  return workspaceId
}, [capabilities, filterWorkspaceId, workspaceId])

const listQuery = useQuery({
  queryKey: ['users', effectiveTenantId, effectiveWorkspaceId, page, pageSize, filters, refreshTick, capabilities?.can_pick_workspace],
  queryFn: async () => {
    setForbidden(false)
    try {
      if (capabilities?.can_pick_workspace && effectiveTenantId && effectiveWorkspaceId) {
        return await listTenantWorkspaceUsers(effectiveTenantId, {
          ...filters,
          workspace_id: effectiveWorkspaceId,
          page,
          page_size: pageSize,
        })
      }
      return await listUsers(workspaceId!, { ...filters, page, page_size: pageSize })
    } catch (e) {
      if (e instanceof ApiError && e.code === 'auth.forbidden') {
        setForbidden(true)
        return { items: [], total: 0, page: 1, page_size: pageSize }
      }
      throw e
    }
  },
  enabled: capabilities
    ? capabilities.can_pick_workspace
      ? Boolean(effectiveTenantId && effectiveWorkspaceId)
      : Boolean(workspaceId)
    : false,
})
```

- [ ] **Step 3: Add scope filter UI**（复制 RolesPage 模式：超管 tenant Select + workspace Select；租户管理员 Tag + workspace Select）

- [ ] **Step 4: Update `openCreate` / `openEdit` / `handleSubmit`**

- `openCreate`：传入 `effectiveWorkspaceId` 作为表单默认 workspace；若 `can_pick_workspace`，预填 `tenant_id`/`workspace_id`。
- `openEdit`：使用 `row.workspace_id` 调 `getUser`；构造 `initialScope`：
```typescript
export type UserScope = {
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
}
```
- `handleSubmit`：编辑时 `patchUser(editingWorkspaceId, ...)` 与 `replaceWorkspaceRoleGrants(tenantId, editingWorkspaceId, ...)` 使用**行所属 workspace**，非 JWT workspace。
- `rolesMetaQuery`：超管/租户管理员用 `effectiveWorkspaceId` 加载角色筛选项。

- [ ] **Step 5: Pass props to `UserFormDrawer`**

```typescript
<UserFormDrawer
  capabilities={capabilities}
  pageWorkspaceId={effectiveWorkspaceId ?? workspaceId}
  initialScope={initialScope}
  tenants={tenants}
  workspaces={formWorkspaces}
  onTenantChange={handleFormTenantChange}
  // ...
/>
```

- [ ] **Step 6: Manual test** — 超管切换 workspace 后列表变化；租户管理员仅见本租户 workspaces。

- [ ] **Step 7: Commit**

```bash
git add frontend/src/features/settings/users/UsersPage.tsx frontend/src/features/settings/users/UsersPage.css
git commit -m "feat(user): add tenant/workspace scope filters and dual list API"
```

---

## Task 8: `UserFormDrawer` scope UI 与角色联动

**Files:**
- Modify: `frontend/src/features/settings/users/UserFormDrawer.tsx`

**参考：** `frontend/src/features/settings/roles/RoleFormDrawer.tsx`

- [ ] **Step 1: Add `UserScope` type and extend Props**

```typescript
export type UserScope = {
  tenant_id: string
  tenant_name: string
  workspace_id: string
  workspace_name: string
}

type Props = {
  // existing...
  capabilities: SysUserListCapabilities | null
  initialScope?: UserScope | null
  tenants?: { id: string; name: string }[]
  workspaces?: { id: string; name: string }[]
  onTenantChange?: (tenantId: string) => void
}
```

- [ ] **Step 2: Replace `showTenantPicker` logic**

```typescript
const showScopeOnCreate =
  mode === 'create' &&
  (capabilities?.can_pick_tenant === true || capabilities?.can_pick_workspace === true)

const showScopeReadonlyOnEdit =
  mode === 'edit' &&
  initialScope != null &&
  capabilities?.can_pick_workspace === true
```

- [ ] **Step 3: Edit mode — disabled Select**（复制 RoleFormDrawer 193–217 行模式，label 用 `users.tenant` / `users.workspace`）

- [ ] **Step 4: Create mode — tenant Tag or Select + workspace Select**

租户管理员：`capabilities.fixed_tenant_name` 显示 Tag。  
超管：tenant Select + `onTenantChange`。  
工作空间管理员：不渲染 scope 区块。

- [ ] **Step 5: Workspace onChange — clear roles**

```typescript
onChange={(wsId: string) => {
  setSelectedWorkspaceId(wsId)
  form.setFieldValue('role_ids', [])
  // reload roles/depts via effectiveWorkspaceId effect
}}
```

Tenant onChange 额外清空 `workspace_id` 与 `role_ids`。

- [ ] **Step 6: Use `listWorkspaces` from `@/api/tenants`** 替代 `listUserFormWorkspaces`（租户管理员可用）；超管 tenant 列表用 `listTenants()`。

- [ ] **Step 7: Edit submit uses `initialScope.workspace_id`**

```typescript
await onSubmit(patch, { targetWorkspaceId: initialScope?.workspace_id ?? pageWorkspaceId! })
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/features/settings/users/UserFormDrawer.tsx
git commit -m "feat(user): align UserFormDrawer scope UI with role management"
```

---

## Task 9: 联调、回归与 spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-user-management-scope-design.md`

- [ ] **Step 1: Backend regression checklist**

| 场景 | 预期 |
|------|------|
| 超管 `workspace-users?workspace_id=X` | 与 `/workspaces/X/users` 一致 |
| 租户管理员访问其他 tenant | 403 |
| 工作空间管理员 | 仍走 `/workspaces/{wid}/users`，无新端点 |
| `GET /sys/tenants/{tid}/users` picker | 不变 |

- [ ] **Step 2: Frontend regression checklist**

| 场景 | 预期 |
|------|------|
| 超管切换 workspace | 列表刷新；新建默认该 workspace |
| 租户管理员 | 固定租户 Tag；workspace 下拉 |
| 编辑用户 | tenant/workspace 只读 |
| 切换 workspace | role_ids 清空 |
| 跨 workspace 创建 | `users.createSuccessOtherWorkspace` 提示 |

- [ ] **Step 3: Run pytest**

```bash
cd backend && python -m pytest tests/sys/user/ -v
```

- [ ] **Step 4: Run frontend typecheck**

```bash
cd frontend && npm run build
```

- [ ] **Step 5: Update spec status**

将 `2026-07-02-user-management-scope-design.md` 状态改为「已实现」并注明日期。

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-07-02-user-management-scope-design.md
git commit -m "docs: mark user management scope spec as implemented"
```

---

## Spec Coverage Self-Review

| Spec 要求 | Task |
|-----------|------|
| 租户级 `workspace-users` API | Task 3, 4 |
| 平台 `capabilities` | Task 1, 2 |
| 列表 scope 筛选（超管/租户管理员） | Task 7 |
| 工作空间管理员不变 | Task 7 list 分支 |
| 新建 scope + 默认跟随列表 | Task 7, 8 |
| 编辑只读 scope | Task 8 |
| 角色联动清空 | Task 8 Step 5 |
| `tenant_name`/`workspace_name` | Task 4, 5 |
| picker 不破坏 | Task 9 回归 |
| i18n 已有 `users.tenant`/`users.workspace` | 无需新 key |

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-02-user-management-scope.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间做 review，迭代快  
2. **Inline Execution** — 在本会话按 Task 顺序执行，批次间设检查点

**你希望用哪种方式开始实现？**
