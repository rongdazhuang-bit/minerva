# 设置页表单权限 UX 优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 优化租户/角色/用户管理新增编辑弹窗：租户新建隐藏管理员；角色菜单树按租户授权过滤；用户表单增加租户管理员 Select、收窄空间管理员编辑权限、角色随工作空间加载。

**Architecture:** 租户模块纯前端调整；角色模块新增租户域 `menu-tree` API 与 create/patch 校验；用户模块新增单用户 tenant-admin API、扩展 capabilities，前端在 `UsersPage` 编排保存顺序。三模块可独立交付，建议按 Task 1 → 2 → 3 → 4 → 5 → 6 顺序。

**Tech Stack:** FastAPI + SQLAlchemy async（后端），React + Ant Design（前端），pytest（后端单元测试）

**Spec:** [docs/superpowers/specs/2026-07-02-settings-forms-permission-ux-design.md](../specs/2026-07-02-settings-forms-permission-ux-design.md)

---

## File Map

| File | Responsibility |
|------|----------------|
| `frontend/src/features/settings/tenants/TenantPermissionFields.tsx` | `showAdmins` prop 控制管理员字段显隐 |
| `frontend/src/features/settings/tenants/TenantFormDrawer.tsx` | 新建跳过 platform users 加载 |
| `frontend/src/features/settings/tenants/TenantsPage.tsx` | 创建时不调用 `putTenantAdmins` |
| `backend/app/sys/role/service/role_service.py` | 租户菜单树裁剪、menu_id 租户校验 |
| `backend/app/sys/role/api/router.py` | `GET /sys/tenants/{tid}/roles/menu-tree` |
| `backend/tests/test_role_service.py` | 菜单树裁剪与校验单元测试 |
| `frontend/src/api/roles.ts` | `listRoleMenuTreeForTenant` |
| `frontend/src/features/settings/roles/RolesPage.tsx` | 按租户加载/切换 menu tree |
| `backend/app/sys/user/service/user_service.py` | `can_edit_membership_role` 收窄、`can_view_membership_role` |
| `backend/app/sys/user/api/schemas.py` | capabilities 新字段 |
| `backend/app/sys/tenant/service/tenant_permission_service.py` | `is_user_tenant_admin`、`set_user_tenant_admin` |
| `backend/app/sys/tenant/api/router.py` | tenant-admin GET/PUT |
| `backend/app/sys/tenant/api/schemas.py` | tenant-admin schema |
| `backend/tests/test_tenant_permission_service.py` | **新建** tenant-admin 服务测试 |
| `frontend/src/api/users.ts` | capabilities 类型、tenant-admin 客户端 |
| `frontend/src/features/settings/users/UserFormDrawer.tsx` | 租户管理员 Select、空间管理员只读、角色禁用 |
| `frontend/src/features/settings/users/UsersPage.tsx` | 编辑加载 tenant-admin、保存编排 |
| `frontend/src/i18n/locales/zh-CN.json` | 新文案 |

---

## Task 1: 租户新建隐藏「租户管理员」

**Files:**
- Modify: `frontend/src/features/settings/tenants/TenantPermissionFields.tsx`
- Modify: `frontend/src/features/settings/tenants/TenantFormDrawer.tsx`
- Modify: `frontend/src/features/settings/tenants/TenantsPage.tsx`

- [ ] **Step 1: 为 `TenantPermissionFields` 增加 `showAdmins`**

```tsx
type Props = {
  menuTree: SysMenuNode[]
  checkedKeys: string[]
  onCheckedKeysChange: (keys: string[]) => void
  userOptions: { value: string; label: string }[]
  adminsHint?: string
  showAdmins?: boolean
}

export function TenantPermissionFields({
  menuTree,
  checkedKeys,
  onCheckedKeysChange,
  userOptions,
  adminsHint,
  showAdmins = true,
}: Props) {
  // ...existing tree UI...
  return (
    <>
      {/* menu tree Form.Item unchanged */}
      {showAdmins ? (
        <Form.Item
          name="admin_user_ids"
          label={t('permissions.adminsLabel')}
          extra={adminsHint ?? t('permissions.adminsHint')}
        >
          <Select /* unchanged */ />
        </Form.Item>
      ) : null}
    </>
  )
}
```

- [ ] **Step 2: `TenantFormDrawer` 新建模式隐藏管理员并跳过 platform users 请求**

在 `TenantFormDrawer.tsx`：

```tsx
<TenantPermissionFields
  menuTree={menuTree}
  checkedKeys={checkedKeys}
  onCheckedKeysChange={setCheckedKeys}
  userOptions={userOptions}
  showAdmins={mode === 'edit'}
  adminsHint={
    mode === 'create'
      ? t('permissions.adminsHintCreate')
      : t('permissions.adminsHint')
  }
/>
```

将 `loadPromise` 新建分支改为仅 `listTenantPermissionMenuTree()`：

```tsx
: Promise.all([listTenantPermissionMenuTree()]).then(([tree]) => {
    if (cancelled) return
    setMenuTree(tree)
    setUserOptions([])
  })
```

- [ ] **Step 3: `TenantsPage.handleSubmit` 创建时跳过 `putTenantAdmins`**

```tsx
} else {
  const created = await createTenant(body)
  await putTenantPermissions(created.id, permissions.menu_ids)
  messageApi.success(t('tenants.createSuccess'))
}
```

编辑分支保持 `putTenantAdmins` 不变。

- [ ] **Step 4: 手工验证**

1. 打开 `/app/settings/tenants` → 新建：确认无「租户管理员」字段，保存成功。
2. 编辑已有租户：确认管理员多选仍可见且可保存。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/features/settings/tenants/TenantPermissionFields.tsx \
  frontend/src/features/settings/tenants/TenantFormDrawer.tsx \
  frontend/src/features/settings/tenants/TenantsPage.tsx
git commit -m "fix(tenants): hide tenant admins field on create form"
```

---

## Task 2: 角色租户菜单树 — 后端

**Files:**
- Modify: `backend/app/sys/role/service/role_service.py`
- Modify: `backend/app/sys/role/api/router.py`
- Modify: `backend/tests/test_role_service.py`

- [ ] **Step 1: Write failing tests for tree pruning and menu validation**

在 `backend/tests/test_role_service.py` 追加：

```python
from app.sys.menu.api.schemas import SysMenuNodeOut
from app.sys.role.service import role_service as svc


def test_collect_menu_ids_with_ancestors_includes_parents() -> None:
    """Authorized leaf menus should pull in ancestor ids for display."""

    root = uuid.uuid4()
    child = uuid.uuid4()
    leaf = uuid.uuid4()
    nodes = [
        SysMenuNodeOut(
            id=root,
            parent_id=None,
            menu_name="Settings",
            menu_type="M",
            path="/settings",
            component=None,
            perms=None,
            icon=None,
            order_num=1,
            status=True,
            visible=True,
            children=[
                SysMenuNodeOut(
                    id=child,
                    parent_id=root,
                    menu_name="Users",
                    menu_type="C",
                    path="users",
                    component=None,
                    perms=None,
                    icon=None,
                    order_num=1,
                    status=True,
                    visible=True,
                    children=[
                        SysMenuNodeOut(
                            id=leaf,
                            parent_id=child,
                            menu_name="List",
                            menu_type="F",
                            path=None,
                            component=None,
                            perms="user:list",
                            icon=None,
                            order_num=1,
                            status=True,
                            visible=True,
                            children=[],
                        )
                    ],
                )
            ],
        )
    ]
    display_ids = svc.collect_menu_display_ids(authorized_ids=[leaf], tree_nodes=nodes)
    assert display_ids == {root, child, leaf}


def test_filter_menu_ids_to_tenant_authorized_strips_ancestor_only() -> None:
    """Persist only tenant-authorized menu ids even if ancestors were checked."""

    root = uuid.uuid4()
    leaf = uuid.uuid4()
    authorized = {leaf}
    submitted = [root, leaf]
    filtered = svc.filter_menu_ids_to_tenant_authorized(
        menu_ids=submitted,
        authorized_ids=authorized,
    )
    assert filtered == [leaf]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_role_service.py::test_collect_menu_ids_with_ancestors_includes_parents tests/test_role_service.py::test_filter_menu_ids_to_tenant_authorized_strips_ancestor_only -v`

Expected: FAIL — `AttributeError: module ... has no attribute 'collect_menu_display_ids'`

- [ ] **Step 3: Implement helpers in `role_service.py`**

在 imports 区域增加 `from app.sys.tenant.service.tenant_permission_service import list_tenant_menu_ids` 与 menu schema 类型。

```python
def collect_menu_display_ids(
    *,
    authorized_ids: list[uuid.UUID],
    tree_nodes: list[SysMenuNodeOut],
) -> set[uuid.UUID]:
    """Return authorized menu ids plus all ancestor ids for tree display."""

    by_id: dict[uuid.UUID, SysMenuNodeOut] = {}

    def walk(nodes: list[SysMenuNodeOut]) -> None:
        for node in nodes:
            by_id[node.id] = node
            if node.children:
                walk(node.children)

    walk(tree_nodes)
    authorized_set = set(authorized_ids)
    display: set[uuid.UUID] = set()
    for mid in authorized_set:
        cur = by_id.get(mid)
        while cur is not None:
            display.add(cur.id)
            cur = by_id.get(cur.parent_id) if cur.parent_id else None
    return display


def prune_menu_tree(
    nodes: list[SysMenuNodeOut],
    *,
    allowed_ids: set[uuid.UUID],
) -> list[SysMenuNodeOut]:
    """Keep nodes in allowed_ids, preserving hierarchy."""

    def walk(items: list[SysMenuNodeOut]) -> list[SysMenuNodeOut]:
        out: list[SysMenuNodeOut] = []
        for node in items:
            children = walk(node.children) if node.children else []
            if node.id in allowed_ids or children:
                out.append(node.model_copy(update={"children": children}))
        return out

    return walk(nodes)


def filter_menu_ids_to_tenant_authorized(
    *,
    menu_ids: list[uuid.UUID],
    authorized_ids: set[uuid.UUID],
) -> list[uuid.UUID]:
    """Drop menu ids outside tenant authorization before persistence."""

    return [mid for mid in menu_ids if mid in authorized_ids]


async def _validate_menu_ids_in_tenant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    menu_ids: list[uuid.UUID],
) -> list[uuid.UUID]:
    """Ensure menu ids exist globally and belong to tenant authorization."""

    if not menu_ids:
        return []
    await _validate_menu_ids(session, menu_ids)
    authorized = set(await list_tenant_menu_ids(session, tenant_id=tenant_id))
    invalid = [str(mid) for mid in menu_ids if mid not in authorized]
    if invalid:
        raise AppError(
            "role.menu_not_in_tenant",
            f"Menu ids not authorized for tenant: {', '.join(invalid)}",
            400,
        )
    return filter_menu_ids_to_tenant_authorized(
        menu_ids=menu_ids,
        authorized_ids=authorized,
    )


async def list_menu_tree_for_tenant_role_assignment(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> list[SysMenuNodeOut]:
    """Return menu tree limited to tenant-authorized menus plus ancestors."""

    authorized_ids = await list_tenant_menu_ids(session, tenant_id=tenant_id)
    full_tree = await list_menu_tree_for_role_assignment(session)
    if not authorized_ids:
        return []
    display_ids = collect_menu_display_ids(
        authorized_ids=authorized_ids,
        tree_nodes=full_tree,
    )
    return prune_menu_tree(full_tree, allowed_ids=display_ids)
```

- [ ] **Step 4: Wire tenant validation into `create_role_for_tenant` and `patch_role_for_tenant`**

在 `create_role_for_tenant` 中，将：

```python
await _validate_menu_ids(session, menu_ids)
```

替换为：

```python
menu_ids = await _validate_menu_ids_in_tenant(
    session,
    tenant_id=tenant_id,
    menu_ids=menu_ids,
)
```

`patch_role_for_tenant`（或等效 patch 路径）中 `menu_ids` 分支同样替换。

- [ ] **Step 5: Add router endpoint**

在 `backend/app/sys/role/api/router.py` 的 `tenant_router` 内、`list_roles_for_tenant` 之前添加：

```python
@tenant_router.get("/menu-tree", response_model=list[SysMenuNodeOut])
async def list_role_menu_tree_for_tenant(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _viewer: uuid.UUID = Depends(require_tenant_role_viewer),
) -> list[SysMenuNodeOut]:
    """Return tenant-scoped menu tree for role permission assignment."""

    return await svc.list_menu_tree_for_tenant_role_assignment(
        session,
        tenant_id=tenant_id,
    )
```

- [ ] **Step 6: Run tests**

Run: `cd backend && python -m pytest tests/test_role_service.py -v`

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/sys/role/service/role_service.py \
  backend/app/sys/role/api/router.py \
  backend/tests/test_role_service.py
git commit -m "feat(roles): tenant-scoped menu tree and menu_id validation"
```

---

## Task 3: 角色菜单树 — 前端联动

**Files:**
- Modify: `frontend/src/api/roles.ts`
- Modify: `frontend/src/features/settings/roles/RolesPage.tsx`
- Modify: `frontend/src/features/settings/roles/RoleFormDrawer.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`

- [ ] **Step 1: Add API client**

在 `frontend/src/api/roles.ts`：

```typescript
/** Load tenant-scoped menu tree for role permission picker. */
export function listRoleMenuTreeForTenant(tenantId: string) {
  return apiJson<SysMenuNode[]>(`/sys/tenants/${tenantId}/roles/menu-tree`)
}
```

- [ ] **Step 2: Replace global `loadMenuTree` with tenant-aware loader in `RolesPage`**

```typescript
import { listRoleMenuTreeForTenant } from '@/api/roles'

const loadMenuTreeForTenant = useCallback(async (tenantIdForTree: string | null) => {
  if (!tenantIdForTree) {
    setMenuTree([])
    return []
  }
  const tree = await listRoleMenuTreeForTenant(tenantIdForTree)
  setMenuTree(tree)
  return tree
}, [])

const pruneCheckedKeys = useCallback((keys: string[], tree: SysMenuNode[]) => {
  const valid = new Set(collectAllKeys(tree))
  return keys.filter((id) => valid.has(id))
}, [])
```

从 `openCreate` 移除 `await loadMenuTree()`；在设置 `initialTenantId` 后：

```typescript
if (initialTenantId) {
  await loadMenuTreeForTenant(initialTenantId)
} else {
  setMenuTree([])
}
```

`openEdit` 改为：

```typescript
await loadMenuTreeForTenant(row.tenant_id)
```

`handleCreateTenantChange` 增加菜单树重载与 checkedKeys 裁剪：

```typescript
const handleCreateTenantChange = useCallback(
  async (tid: string) => {
    setCreateTenantId(tid)
    const tree = await loadMenuTreeForTenant(tid)
    setInitialMenuIds((prev) => pruneCheckedKeys(prev, tree))
    await loadCreateWorkspaces(tid)
  },
  [loadCreateWorkspaces, loadMenuTreeForTenant, pruneCheckedKeys],
)
```

将 `collectAllKeys` 从 `RoleFormDrawer` 提取到共享 util，或在 `RolesPage` 内联复制现有实现。

- [ ] **Step 3: Optional empty-state hint in `RoleFormDrawer`**

新增 prop `menuTreeHint?: string | null`；当 `menuTree.length === 0` 时在菜单权限区展示 Alert。

`RolesPage` 传入：`menuTreeHint={drawerMode === 'create' && !createTenantId ? t('roles.selectTenantForMenus') : null}`

i18n 新增：`"roles.selectTenantForMenus": "请先选择租户以加载菜单权限"`

- [ ] **Step 4: 手工验证**

1. 超管角色新建：切换租户 → 菜单树变化。
2. 编辑角色：树仅含该租户授权菜单及祖先。
3. 勾选祖先节点保存：后端仅持久化租户授权 leaf/menu id。

- [ ] **Step 5: Commit**

```bash
git add frontend/src/api/roles.ts \
  frontend/src/features/settings/roles/RolesPage.tsx \
  frontend/src/features/settings/roles/RoleFormDrawer.tsx \
  frontend/src/i18n/locales/zh-CN.json
git commit -m "feat(roles): load menu tree by selected tenant in form"
```

---

## Task 4: 用户 capabilities — 收窄空间管理员编辑

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`
- Modify: `backend/app/sys/user/api/schemas.py`
- Modify: `frontend/src/api/users.ts`
- Create: `backend/tests/test_user_membership_capabilities.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_user_membership_capabilities.py
from app.sys.user.service.user_service import can_edit_membership_role


def test_workspace_admin_cannot_edit_membership_role() -> None:
    assert (
        can_edit_membership_role(
            actor_workspace_role="admin",
            actor_is_super_admin=False,
            actor_is_tenant_admin=False,
            actor_has_workspace_membership=True,
        )
        is False
    )


def test_tenant_admin_can_edit_membership_role() -> None:
    assert (
        can_edit_membership_role(
            actor_workspace_role=None,
            actor_is_super_admin=False,
            actor_is_tenant_admin=True,
            actor_has_workspace_membership=False,
        )
        is True
    )
```

- [ ] **Step 2: Run test — expect FAIL**（现网 workspace admin 仍返回 True）

Run: `cd backend && python -m pytest tests/test_user_membership_capabilities.py -v`

- [ ] **Step 3: Update `can_edit_membership_role` and add `can_view_membership_role`**

```python
def can_view_membership_role(
    *,
    actor_is_super_admin: bool,
    actor_is_tenant_admin: bool,
    actor_workspace_role: MembershipRole | None,
    actor_has_workspace_membership: bool,
) -> bool:
    """True when membership_role field should appear on the user form."""

    if actor_is_super_admin or actor_is_tenant_admin:
        return True
    return actor_workspace_role == MembershipRole.admin


def can_edit_membership_role(
    *,
    actor_workspace_role: MembershipRole | None,
    actor_is_super_admin: bool,
    actor_is_tenant_admin: bool,
    actor_has_workspace_membership: bool,
) -> bool:
    """True when the actor may change membership_role on create or patch."""

    return actor_is_super_admin or actor_is_tenant_admin
```

在 `get_user_capabilities` / `build_user_list_capabilities` 返回值中加入：

```python
"can_view_membership_role": can_view,
"can_edit_tenant_admin": is_super_admin,
```

`SysUserCapabilitiesOut` 与 `SysUserListCapabilitiesOut` 增加字段：

```python
can_view_membership_role: bool = False
can_edit_tenant_admin: bool = False
```

- [ ] **Step 4: Update frontend types in `frontend/src/api/users.ts`**

```typescript
export type SysUserCapabilities = {
  // ...existing...
  can_view_membership_role: boolean
  can_edit_tenant_admin: boolean
}

export type SysUserListCapabilities = {
  // ...existing...
  can_edit_tenant_admin: boolean
  can_view_membership_role: boolean
}
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_user_membership_capabilities.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/sys/user/service/user_service.py \
  backend/app/sys/user/api/schemas.py \
  backend/tests/test_user_membership_capabilities.py \
  frontend/src/api/users.ts
git commit -m "feat(users): narrow membership edit to super/tenant admin"
```

---

## Task 5: 单用户 tenant-admin API — 后端

**Files:**
- Modify: `backend/app/sys/tenant/service/tenant_permission_service.py`
- Modify: `backend/app/sys/tenant/api/schemas.py`
- Modify: `backend/app/sys/tenant/api/router.py`
- Create: `backend/tests/test_tenant_permission_service.py`

- [ ] **Step 1: Write failing tests**

```python
# backend/tests/test_tenant_permission_service.py
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.sys.tenant.service import tenant_permission_service as svc


@pytest.mark.asyncio
async def test_set_user_tenant_admin_enable_adds_grant(monkeypatch) -> None:
    session = AsyncMock()
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    actor_id = uuid.uuid4()

    monkeypatch.setattr(
        "app.sys.tenant.service.tenant_permission_service.tenant_svc.get_tenant",
        AsyncMock(return_value=MagicMock()),
    )
    session.get = AsyncMock(return_value=MagicMock())
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=lambda: None)
    )
    session.add = MagicMock()
    session.commit = AsyncMock()

    result = await svc.set_user_tenant_admin(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        enabled=True,
        granted_by_user_id=actor_id,
    )
    assert result is True
    session.add.assert_called_once()
    session.commit.assert_awaited_once()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd backend && python -m pytest tests/test_tenant_permission_service.py -v`

- [ ] **Step 3: Implement service functions**

在 `tenant_permission_service.py`：

```python
async def is_user_tenant_admin(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Return whether the user holds tenant_admin grant for the tenant."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    r = await session.execute(
        select(SysUserGrant.id).where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
            SysUserGrant.status.is_(True),
        )
    )
    return r.scalar_one_or_none() is not None


async def set_user_tenant_admin(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    enabled: bool,
    granted_by_user_id: uuid.UUID,
) -> bool:
    """Enable or disable tenant_admin grant for one user."""

    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    user = await session.get(User, user_id)
    if user is None:
        raise AppError("user.not_found", "User not found", 404)

    r = await session.execute(
        select(SysUserGrant).where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.tenant_admin.value,
            SysUserGrant.scope_type == GrantScopeType.tenant.value,
            SysUserGrant.scope_id == tenant_id,
        )
    )
    row = r.scalar_one_or_none()
    now = _utc_now()

    if enabled:
        if row is None:
            session.add(
                SysUserGrant(
                    user_id=user_id,
                    grant_type=GrantType.tenant_admin.value,
                    scope_type=GrantScopeType.tenant.value,
                    scope_id=tenant_id,
                    granted_by_user_id=granted_by_user_id,
                    status=True,
                    create_at=now,
                    update_at=now,
                )
            )
        else:
            row.status = True
            row.update_at = now
        await session.commit()
        return True

    if row is not None:
        await session.delete(row)
        await session.commit()
    return False
```

- [ ] **Step 4: Add schemas and routes**

`schemas.py`：

```python
class SysTenantAdminStatusOut(BaseModel):
    is_tenant_admin: bool


class SysTenantAdminPutIn(BaseModel):
    enabled: bool
```

`router.py`（`require_super_admin`）：

```python
@router.get(
    "/{tenant_id}/users/{user_id}/tenant-admin",
    response_model=SysTenantAdminStatusOut,
)
async def get_user_tenant_admin(...):
    is_admin = await permission_svc.is_user_tenant_admin(
        session, tenant_id=tenant_id, user_id=user_id
    )
    return SysTenantAdminStatusOut(is_tenant_admin=is_admin)


@router.put(
    "/{tenant_id}/users/{user_id}/tenant-admin",
    response_model=SysTenantAdminStatusOut,
)
async def put_user_tenant_admin(..., body: SysTenantAdminPutIn):
    is_admin = await permission_svc.set_user_tenant_admin(
        session,
        tenant_id=tenant_id,
        user_id=user_id,
        enabled=body.enabled,
        granted_by_user_id=admin.id,
    )
    return SysTenantAdminStatusOut(is_tenant_admin=is_admin)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && python -m pytest tests/test_tenant_permission_service.py tests/test_user_membership_capabilities.py -v`

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/sys/tenant/service/tenant_permission_service.py \
  backend/app/sys/tenant/api/schemas.py \
  backend/app/sys/tenant/api/router.py \
  backend/tests/test_tenant_permission_service.py
git commit -m "feat(tenants): single-user tenant-admin get/put API"
```

---

## Task 6: 用户表单 — 前端

**Files:**
- Modify: `frontend/src/api/users.ts`
- Modify: `frontend/src/features/settings/users/UserFormDrawer.tsx`
- Modify: `frontend/src/features/settings/users/UsersPage.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`

- [ ] **Step 1: Add tenant-admin API client**

在 `frontend/src/api/users.ts`（或 `tenantPermissions.ts`）：

```typescript
export type SysTenantAdminStatus = { is_tenant_admin: boolean }

export function getUserTenantAdmin(tenantId: string, userId: string) {
  return apiJson<SysTenantAdminStatus>(
    `/sys/tenants/${tenantId}/users/${userId}/tenant-admin`,
  )
}

export function putUserTenantAdmin(
  tenantId: string,
  userId: string,
  enabled: boolean,
) {
  return apiJson<SysTenantAdminStatus>(
    `/sys/tenants/${tenantId}/users/${userId}/tenant-admin`,
    { method: 'PUT', body: JSON.stringify({ enabled }) },
  )
}
```

- [ ] **Step 2: Extend `UserFormValues` and form UI**

`UserFormDrawer.tsx`：

```typescript
export type UserFormValues = {
  // ...existing...
  tenant_admin_role?: 'admin' | 'member'
}

const effectiveTenantId = useMemo(() => {
  if (showScopeOnCreate) return selectedTenantId ?? null
  if (showScopeReadonlyOnEdit && initialScope) return initialScope.tenant_id
  return listCapabilities?.fixed_tenant_id ?? null
}, [/* deps */])
```

初始化表单：

```typescript
tenant_admin_role: initial?.tenant_admin_role ?? 'member',
```

渲染租户管理员（仅超管 + 有 tenant）：

```tsx
{listCapabilities?.can_edit_tenant_admin && effectiveTenantId ? (
  <Form.Item
    name="tenant_admin_role"
    label={t('users.tenantAdminRole')}
    initialValue="member"
  >
    <Select
      allowClear={false}
      options={[
        { value: 'member', label: t('users.membershipMember') },
        { value: 'admin', label: t('users.membershipAdmin') },
      ]}
    />
  </Form.Item>
) : null}
```

空间管理员区块改为：

```tsx
{formCapabilities?.can_view_membership_role ? (
  formCapabilities.can_edit_membership_role ? (
    <Form.Item name="membership_role" label={t('users.workspaceAdminRole')} /* Select */ />
  ) : (
    <Form.Item label={t('users.workspaceAdminRole')}>
      <Select
        disabled
        value={initial?.membership_role ?? 'member'}
        options={[/* admin/member labels */]}
      />
    </Form.Item>
  )
) : null}
```

角色 Select 增加 disabled：

```tsx
<Select
  disabled={!effectiveWorkspaceId}
  placeholder={
    effectiveWorkspaceId
      ? t('users.rolesPlaceholder')
      : t('users.rolesSelectWorkspaceFirst')
  }
  /* ... */
/>
```

i18n：

```json
"users.tenantAdminRole": "租户管理员",
"users.workspaceAdminRole": "空间管理员",
"users.rolesSelectWorkspaceFirst": "请先选择工作空间"
```

- [ ] **Step 3: `UsersPage` 编辑加载 tenant-admin 与保存编排**

打开编辑时（超管）：

```typescript
let tenantAdminRole: 'admin' | 'member' = 'member'
if (capabilities?.can_edit_tenant_admin && scopeTenantId) {
  const status = await getUserTenantAdmin(scopeTenantId, row.user_id)
  tenantAdminRole = status.is_tenant_admin ? 'admin' : 'member'
}
setInitialForm({
  // ...existing...
  tenant_admin_role: tenantAdminRole,
})
```

`handleSubmit` 成功后：

```typescript
if (
  listCapabilities?.can_edit_tenant_admin &&
  scopeTenantId &&
  values.tenant_admin_role != null
) {
  const enabled = values.tenant_admin_role === 'admin'
  const initialEnabled = initialForm?.tenant_admin_role === 'admin'
  if (enabled !== initialEnabled) {
    await putUserTenantAdmin(scopeTenantId, savedUserId, enabled)
  }
}
```

新建用户：`savedUserId` 来自 `createUser` 响应的 `id`。

- [ ] **Step 4: 手工验证矩阵**

| 场景 | 预期 |
|------|------|
| 超管新建用户 | 可见租户管理员 Select，默认成员；选工作空间后角色可加载 |
| 超管编辑用户 | 租户管理员回显正确；修改后 grant 更新 |
| 租户管理员 | 可见空间管理员可编辑；无租户管理员字段 |
| 工作空间管理员 | 空间管理员只读；无租户管理员字段 |

- [ ] **Step 5: Update spec status**

将 `docs/superpowers/specs/2026-07-02-settings-forms-permission-ux-design.md` 状态改为「已实现」。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/users.ts \
  frontend/src/features/settings/users/UserFormDrawer.tsx \
  frontend/src/features/settings/users/UsersPage.tsx \
  frontend/src/i18n/locales/zh-CN.json \
  docs/superpowers/specs/2026-07-02-settings-forms-permission-ux-design.md
git commit -m "feat(users): tenant admin select and membership visibility rules"
```

---

## Spec Coverage Self-Review

| Spec 要求 | Task |
|-----------|------|
| 租户新建隐藏管理员 | Task 1 |
| 角色菜单按租户过滤 + 保存校验 | Task 2, 3 |
| 角色随 workspace 加载 | Task 6 Step 2 |
| 租户管理员 Select（超管） | Task 4, 5, 6 |
| 空间管理员可见性收窄 | Task 4, 6 |
| tenant-admin API | Task 5 |
| capabilities 扩展 | Task 4 |
| i18n | Task 3, 6 |

无 TBD / 占位步骤。

---

**Plan complete and saved to `docs/superpowers/plans/2026-07-02-settings-forms-permission-ux.md`.**

两种执行方式：

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，任务间 review，迭代快  
2. **Inline Execution** — 在本会话按 Task 顺序直接实现，批次间 checkpoint

你选哪种？
