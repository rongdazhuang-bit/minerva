# 租户管理页 UX 与租户菜单授权 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将租户授权从 `feature_code` 迁移为 `menu_id`（`sys_tenant_permission`），授权抽屉改为菜单 Tree，租户管理员改为成员多选下拉，并调整操作列删除按钮顺序。

**Architecture:** SQL patch 重命名表与列并迁移历史数据；`tenant_permission_service` 读写 `menu_ids`；`authorization/repository` 由 menu_id 推导 `tenant_features` 供现有 `make_require_feature_workspace` 使用；侧栏在角色过滤后再与租户菜单求交；前端 `TenantPermissionDrawer` 对齐 `RoleFormDrawer` Tree 交互。

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL patch, pytest, React 18, TanStack Query, Ant Design Tree/Select

**Spec:** `docs/superpowers/specs/2026-07-01-tenant-page-ux-design.md`

---

## File Map

| 文件 | 职责 |
|------|------|
| `backend/sql/patches/2026-07-01-sys-tenant-permission-rename.sql` | 表重命名 + 列迁移 + 数据映射 |
| `backend/sql/tables/sys_tenant_permission.sql` | 新表 DDL（替代 `sys_tenant_entitlement.sql`） |
| `backend/sql/schema_postgresql.sql` | 同步全库定义 |
| `backend/scripts/generate_schema_column_comments.py` | 表/列注释 |
| `backend/app/core/domain/authorization/models.py` | `SysTenantPermission` ORM |
| `backend/app/core/domain/authorization/repository.py` | menu_id 加载 + feature 推导 |
| `backend/app/core/security/permission_codes.py` | `menu_key_to_feature()` 映射 |
| `backend/app/sys/tenant/service/tenant_permission_service.py` | 租户菜单权限 + tenant admin CRUD |
| `backend/app/sys/tenant/infrastructure/repository.py` | `list_tenant_users()` |
| `backend/app/sys/tenant/api/schemas.py` | permissions / users schema |
| `backend/app/sys/tenant/api/router.py` | `/permissions`、`/users` 路由 |
| `backend/app/sys/menu/service/menu_service.py` | 侧栏租户菜单交集 |
| `backend/tests/test_tenant_permission_api.py` | permissions API 测试 |
| `backend/tests/test_tenant_users_api.py` | users API 测试 |
| `backend/tests/test_tenant_feature_derivation.py` | menu→feature 纯函数测试 |
| `frontend/src/api/tenantPermissions.ts` | 新 API 客户端 |
| `frontend/src/features/settings/tenants/TenantPermissionDrawer.tsx` | 授权抽屉（Tree + 用户多选） |
| `frontend/src/features/settings/tenants/TenantsPage.tsx` | 操作列顺序 + 引用新 Drawer |
| `frontend/src/i18n/locales/zh-CN.json` / `en.json` | i18n |

**删除 / 废弃：**

- `backend/sql/tables/sys_tenant_entitlement.sql`
- `backend/app/sys/tenant/service/entitlement_service.py`（逻辑迁入 `tenant_permission_service.py`）
- `frontend/src/api/tenantEntitlements.ts`
- `frontend/src/features/settings/tenants/TenantEntitlementDrawer.tsx`

---

## Task 1: SQL patch — `sys_tenant_permission`

**Files:**
- Create: `backend/sql/patches/2026-07-01-sys-tenant-permission-rename.sql`
- Create: `backend/sql/tables/sys_tenant_permission.sql`
- Delete: `backend/sql/tables/sys_tenant_entitlement.sql`
- Modify: `backend/sql/schema_postgresql.sql`（替换 entitlement 段为 permission 段）

- [ ] **Step 1: 编写 patch**

`backend/sql/patches/2026-07-01-sys-tenant-permission-rename.sql`：

```sql
-- Rename sys_tenant_entitlement -> sys_tenant_permission; feature_code -> menu_id; granted_by_user_id -> create_by
-- Prerequisites: unified-permission-gateway P0 patch applied

ALTER TABLE public.sys_tenant_entitlement RENAME TO sys_tenant_permission;

ALTER TABLE public.sys_tenant_permission ADD COLUMN IF NOT EXISTS menu_id UUID NULL;

-- Map legacy feature_code rows to sys_menu.id via menu_key
UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:agent' AND m.menu_key = 'sub-agents';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:dataset' AND m.menu_key = 'sub-dataset';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:ocr' AND m.menu_key = 'sub-file-ocr';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:skills' AND m.menu_key = 'agents-skills';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:translate' AND m.menu_key = 'sub-doc-translate';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:rules' AND m.menu_key = 'sub-rules';

UPDATE public.sys_tenant_permission tp
SET menu_id = m.id
FROM public.sys_menu m
WHERE tp.feature_code = 'feature:file_storage' AND m.menu_key = 'settings-file-storage';

DELETE FROM public.sys_tenant_permission WHERE menu_id IS NULL;

ALTER TABLE public.sys_tenant_permission DROP COLUMN IF EXISTS feature_code;
ALTER TABLE public.sys_tenant_permission ALTER COLUMN menu_id SET NOT NULL;

ALTER TABLE public.sys_tenant_permission
  RENAME COLUMN granted_by_user_id TO create_by;

DROP INDEX IF EXISTS public.uq_sys_tenant_entitlement_tenant_feature;
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_tenant_permission_tenant_menu
  ON public.sys_tenant_permission (tenant_id, menu_id);

COMMENT ON TABLE public.sys_tenant_permission IS '租户菜单开通（超管授权）';
COMMENT ON COLUMN public.sys_tenant_permission.menu_id IS '逻辑引用 sys_menu.id';
COMMENT ON COLUMN public.sys_tenant_permission.create_by IS '创建人用户 id';
```

- [ ] **Step 2: 新建 `backend/sql/tables/sys_tenant_permission.sql`**

```sql
CREATE TABLE IF NOT EXISTS public.sys_tenant_permission (
  id         UUID         NOT NULL,
  tenant_id  UUID         NOT NULL,
  menu_id    UUID         NOT NULL,
  enabled    BOOLEAN      NOT NULL DEFAULT true,
  create_by  UUID         NOT NULL,
  create_at  TIMESTAMPTZ  NULL DEFAULT now(),
  update_at  TIMESTAMPTZ  NULL,
  CONSTRAINT sys_tenant_permission_pk PRIMARY KEY (id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_sys_tenant_permission_tenant_menu
  ON public.sys_tenant_permission (tenant_id, menu_id);
CREATE INDEX IF NOT EXISTS ix_sys_tenant_permission_tenant_id
  ON public.sys_tenant_permission (tenant_id);
```

- [ ] **Step 3: 同步 `schema_postgresql.sql`**（搜索 `sys_tenant_entitlement` 整段替换）

- [ ] **Step 4: 更新 `generate_schema_column_comments.py`**

将 `"sys_tenant_entitlement"` 键改为 `"sys_tenant_permission"`，`feature_code` → `menu_id`，`granted_by_user_id` → `create_by`。

---

## Task 2: ORM — `SysTenantPermission`

**Files:**
- Modify: `backend/app/core/domain/authorization/models.py`
- Modify: `backend/app/core/domain/authorization/repository.py`（import 更名）

- [ ] **Step 1: 替换 ORM 类**

在 `models.py` 将 `SysTenantEntitlement` 改为：

```python
class SysTenantPermission(Base):
    """Menu nodes enabled for one tenant by platform super admin."""

    __tablename__ = "sys_tenant_permission"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "menu_id",
            name="uq_sys_tenant_permission_tenant_menu",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    menu_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), index=True, nullable=False
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.true()
    )
    create_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    create_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=True
    )
    update_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
```

- [ ] **Step 2: 全局替换 import**

`grep -r SysTenantEntitlement backend/app` → 全部改为 `SysTenantPermission`，字段 `feature_code` → `menu_id`，`granted_by_user_id` → `create_by`（**仅** `sys_tenant_permission` 相关，勿改 `SysUserGrant`）。

---

## Task 3: `menu_key_to_feature` 推导函数（TDD）

**Files:**
- Modify: `backend/app/core/security/permission_codes.py`
- Create: `backend/tests/test_tenant_feature_derivation.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_tenant_feature_derivation.py`：

```python
from app.core.security.permission_codes import menu_key_to_feature, derive_tenant_features_from_menu_keys


def test_menu_key_to_feature_agent_subtree():
    assert menu_key_to_feature("sub-agents") == "feature:agent"
    assert menu_key_to_feature("agents-chat") == "feature:agent"
    assert menu_key_to_feature("agents-mcp") == "feature:agent"


def test_menu_key_to_feature_skills():
    assert menu_key_to_feature("agents-skills") == "feature:skills"


def test_menu_key_to_feature_dataset():
    assert menu_key_to_feature("sub-dataset") == "feature:dataset"
    assert menu_key_to_feature("dataset-list") == "feature:dataset"


def test_menu_key_to_feature_unmapped():
    assert menu_key_to_feature("sub-settings") is None
    assert menu_key_to_feature("overview") is None


def test_derive_tenant_features_dedupes():
    keys = ["sub-agents", "agents-chat", "agents-skills", "sub-dataset"]
    assert derive_tenant_features_from_menu_keys(keys) == frozenset(
        {"feature:agent", "feature:skills", "feature:dataset"}
    )
```

- [ ] **Step 2: 运行确认失败**

```bash
cd backend && python -m pytest tests/test_tenant_feature_derivation.py -v
```

Expected: `ImportError` 或 `AttributeError`

- [ ] **Step 3: 实现**

在 `permission_codes.py` 追加：

```python
import fnmatch


def menu_key_to_feature(menu_key: str | None) -> str | None:
    """Map one sys_menu.menu_key to a platform feature_code, if any."""

    if not menu_key:
        return None
    if menu_key == "agents-skills":
        return FEATURE_SKILLS
    if menu_key == "sub-agents" or fnmatch.fnmatch(menu_key, "agents-*"):
        return FEATURE_AGENT
    if menu_key == "sub-dataset" or fnmatch.fnmatch(menu_key, "dataset-*"):
        return FEATURE_DATASET
    if menu_key == "sub-file-ocr" or fnmatch.fnmatch(menu_key, "file-ocr-*"):
        return FEATURE_OCR
    if menu_key == "sub-doc-translate" or fnmatch.fnmatch(menu_key, "doc-translate-*"):
        return FEATURE_TRANSLATE
    if menu_key == "sub-rules" or fnmatch.fnmatch(menu_key, "rules-*"):
        return FEATURE_RULES
    if menu_key == "settings-file-storage":
        return FEATURE_FILE_STORAGE
    return None


def derive_tenant_features_from_menu_keys(menu_keys: list[str]) -> frozenset[str]:
    """Derive enabled feature codes from a list of menu_key values."""

    out: set[str] = set()
    for key in menu_keys:
        code = menu_key_to_feature(key)
        if code:
            out.add(code)
    return frozenset(out)
```

- [ ] **Step 4: 运行确认通过**

```bash
cd backend && python -m pytest tests/test_tenant_feature_derivation.py -v
```

Expected: 5 passed

---

## Task 4: Repository — 加载 menu_id 并推导 features

**Files:**
- Modify: `backend/app/core/domain/authorization/repository.py`

- [ ] **Step 1: 新增 `load_enabled_tenant_menu_ids`**

```python
async def load_enabled_tenant_menu_ids(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[uuid.UUID]:
    """Return enabled menu_id values for a tenant."""

    r = await session.execute(
        select(SysTenantPermission.menu_id).where(
            SysTenantPermission.tenant_id == tenant_id,
            SysTenantPermission.enabled.is_(True),
        )
    )
    return list(r.scalars().all())
```

- [ ] **Step 2: 改写 `load_enabled_tenant_features`**

```python
async def load_enabled_tenant_features(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[str]:
    """Return derived feature_code values from tenant menu permissions."""

    menu_ids = await load_enabled_tenant_menu_ids(session, tenant_id=tenant_id)
    if not menu_ids:
        return []
    r = await session.execute(
        select(SysMenu.menu_key).where(SysMenu.id.in_(menu_ids))
    )
    keys = [k for k in r.scalars().all() if k]
    return sorted(derive_tenant_features_from_menu_keys(keys))
```

需在文件顶部 import `SysMenu`、`SysTenantPermission`、`derive_tenant_features_from_menu_keys`。

- [ ] **Step 3: 确认 resolver 无需改签名**

`permission_resolver.py` 仍调用 `load_enabled_tenant_features` — 行为自动切换为 menu 推导。

---

## Task 5: `tenant_permission_service` + 删除旧 service

**Files:**
- Create: `backend/app/sys/tenant/service/tenant_permission_service.py`
- Delete: `backend/app/sys/tenant/service/entitlement_service.py`
- Modify: `backend/app/sys/tenant/api/router.py`（import 路径）

- [ ] **Step 1: 实现 service**

`tenant_permission_service.py` 核心逻辑：

```python
async def list_tenant_menu_ids(session, *, tenant_id: uuid.UUID) -> list[uuid.UUID]:
    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    r = await session.execute(
        select(SysTenantPermission.menu_id).where(
            SysTenantPermission.tenant_id == tenant_id,
            SysTenantPermission.enabled.is_(True),
        )
    )
    return list(r.scalars().all())


async def replace_tenant_permissions(
    session,
    *,
    tenant_id: uuid.UUID,
    menu_ids: list[uuid.UUID],
    create_by: uuid.UUID,
) -> list[uuid.UUID]:
    await tenant_svc.get_tenant(session, tenant_id=tenant_id)
    unique_ids = list(dict.fromkeys(menu_ids))
    if unique_ids:
        r = await session.execute(
            select(SysMenu.id).where(SysMenu.id.in_(unique_ids))
        )
        found = set(r.scalars().all())
        invalid = [str(m) for m in unique_ids if m not in found]
        if invalid:
            raise AppError(
                "tenant.invalid_menu",
                f"Unknown menu ids: {', '.join(invalid)}",
                400,
            )
    await session.execute(
        delete(SysTenantPermission).where(SysTenantPermission.tenant_id == tenant_id)
    )
    now = _utc_now()
    for mid in unique_ids:
        session.add(
            SysTenantPermission(
                tenant_id=tenant_id,
                menu_id=mid,
                enabled=True,
                create_by=create_by,
                create_at=now,
                update_at=now,
            )
        )
    await session.commit()
    return unique_ids
```

`list_tenant_admin_user_ids` / `replace_tenant_admins` 从旧 `entitlement_service.py` **原样迁入**（仅改 import）。

- [ ] **Step 2: 删除 `entitlement_service.py`**

- [ ] **Step 3: router import 改为 `tenant_permission_service as permission_svc`**

---

## Task 6: API schemas + router

**Files:**
- Modify: `backend/app/sys/tenant/api/schemas.py`
- Modify: `backend/app/sys/tenant/api/router.py`
- Modify: `backend/app/sys/tenant/infrastructure/repository.py`

- [ ] **Step 1: schemas**

替换 entitlement schema：

```python
class SysTenantPermissionsOut(BaseModel):
    menu_ids: list[uuid.UUID]


class SysTenantPermissionsPutIn(BaseModel):
    menu_ids: list[uuid.UUID]


class SysTenantUserOptionOut(BaseModel):
    id: uuid.UUID
    nickname: str
    email: str
    status: bool


class SysTenantUserListOut(BaseModel):
    items: list[SysTenantUserOptionOut]
```

删除 `SysTenantEntitlementsOut` / `SysTenantEntitlementsPutIn`。

- [ ] **Step 2: `list_tenant_users` repository**

在 `repository.py`：

```python
from app.core.domain.identity.models import TenantMembership, User

async def list_tenant_users(
    session: AsyncSession, *, tenant_id: uuid.UUID
) -> list[User]:
    r = await session.execute(
        select(User)
        .join(TenantMembership, TenantMembership.user_id == User.id)
        .where(TenantMembership.tenant_id == tenant_id)
        .order_by(User.nickname.asc(), User.email.asc())
    )
    return list(r.scalars().all())
```

- [ ] **Step 3: router 路由**

```python
@router.get("/{tenant_id}/permissions", response_model=SysTenantPermissionsOut)
async def get_tenant_permissions(...):
    ids = await permission_svc.list_tenant_menu_ids(session, tenant_id=tenant_id)
    return SysTenantPermissionsOut(menu_ids=ids)


@router.put("/{tenant_id}/permissions", response_model=SysTenantPermissionsOut)
async def put_tenant_permissions(
    body: SysTenantPermissionsPutIn, admin: User = Depends(require_super_admin), ...
):
    ids = await permission_svc.replace_tenant_permissions(
        session,
        tenant_id=tenant_id,
        menu_ids=body.menu_ids,
        create_by=admin.id,
    )
    return SysTenantPermissionsOut(menu_ids=ids)


@router.get("/{tenant_id}/users", response_model=SysTenantUserListOut)
async def list_tenant_users_for_form(...):
    rows = await repo.list_tenant_users(session, tenant_id=tenant_id)
    return SysTenantUserListOut(
        items=[
            SysTenantUserOptionOut(
                id=u.id, nickname=u.nickname, email=u.email, status=u.status
            )
            for u in rows
        ]
    )
```

删除 `/entitlements` 两个端点（不保留别名）。

---

## Task 7: 侧栏租户菜单交集

**Files:**
- Modify: `backend/app/sys/menu/service/menu_service.py`

- [ ] **Step 1: 更新 `list_nav_tree_for_user`**

在角色过滤分支（非超管）中：

```python
from app.core.domain.authorization.repository import load_enabled_tenant_menu_ids

# 已有 ctx.menu_ids 来自角色
tenant_menu_ids: set[uuid.UUID] = set()
if tenant_id is not None:
    tenant_menu_ids = set(
        await load_enabled_tenant_menu_ids(session, tenant_id=tenant_id)
    )

rows = await repo.list_all(session)
nav_rows = filter_nav_rows(rows)

role_expanded = expand_allowed_nav_menu_ids(nav_rows, set(ctx.menu_ids))
if tenant_id is not None and tenant_menu_ids:
    tenant_expanded = expand_allowed_nav_menu_ids(nav_rows, tenant_menu_ids)
    allowed = role_expanded & tenant_expanded
else:
    allowed = role_expanded

return build_menu_tree(filter_rows_by_menu_ids(nav_rows, allowed))
```

超管分支（`ctx.is_super_admin`）保持返回全量 `nav_rows` 树。

---

## Task 8: API 测试

**Files:**
- Create: `backend/tests/test_tenant_permission_api.py`
- Create: `backend/tests/test_tenant_users_api.py`
- Create: `backend/tests/conftest.py`（若不存在，提供 async client + super_admin override 夹具，对齐项目既有测试模式）

- [ ] **Step 1: `test_tenant_permission_api.py`**

覆盖：
- 非超管 `GET/PUT /sys/tenants/{id}/permissions` → 403
- 超管 PUT 合法 `menu_ids` → GET 回显一致
- PUT 含不存在 menu_id → 400 `tenant.invalid_menu`
- 租户不存在 → 404

- [ ] **Step 2: `test_tenant_users_api.py`**

覆盖：
- 超管 GET `/users` 返回该租户成员
- 非超管 403

- [ ] **Step 3: 运行**

```bash
cd backend && python -m pytest tests/test_tenant_permission_api.py tests/test_tenant_users_api.py -v
```

---

## Task 9: 前端 API 客户端

**Files:**
- Create: `frontend/src/api/tenantPermissions.ts`
- Delete: `frontend/src/api/tenantEntitlements.ts`

- [ ] **Step 1: 新建 `tenantPermissions.ts`**

```typescript
import { apiJson } from '@/api/client'
import type { SysMenuNode } from '@/api/menus'
import { listMenus } from '@/api/menus'

export type SysTenantPermissions = { menu_ids: string[] }

export type SysTenantUserOption = {
  id: string
  nickname: string
  email: string
  status: boolean
}

export function getTenantPermissions(tenantId: string) {
  return apiJson<SysTenantPermissions>(`/sys/tenants/${tenantId}/permissions`)
}

export function putTenantPermissions(tenantId: string, menu_ids: string[]) {
  return apiJson<SysTenantPermissions>(`/sys/tenants/${tenantId}/permissions`, {
    method: 'PUT',
    body: JSON.stringify({ menu_ids }),
  })
}

export function getTenantAdmins(tenantId: string) {
  return apiJson<{ user_ids: string[] }>(`/sys/tenants/${tenantId}/admins`)
}

export function putTenantAdmins(tenantId: string, user_ids: string[]) {
  return apiJson<{ user_ids: string[] }>(`/sys/tenants/${tenantId}/admins`, {
    method: 'PUT',
    body: JSON.stringify({ user_ids }),
  })
}

export function listTenantUsers(tenantId: string) {
  return apiJson<{ items: SysTenantUserOption[] }>(
    `/sys/tenants/${tenantId}/users`,
  )
}

/** Load full sys_menu tree for tenant permission picker (same as menu config). */
export function listTenantPermissionMenuTree(): Promise<SysMenuNode[]> {
  return listMenus()
}
```

- [ ] **Step 2: 删除 `tenantEntitlements.ts`，grep 全 frontend 替换 import**

---

## Task 10: `TenantPermissionDrawer.tsx`

**Files:**
- Create: `frontend/src/features/settings/tenants/TenantPermissionDrawer.tsx`
- Create: `frontend/src/features/settings/tenants/menuTreeUtils.ts`（从 `RoleFormDrawer` 复制 `buildTreeData` / `collectAllKeys`）
- Delete: `frontend/src/features/settings/tenants/TenantEntitlementDrawer.tsx`

- [ ] **Step 1: `menuTreeUtils.ts`**

从 `RoleFormDrawer.tsx` 复制 `collectAllKeys`、`buildTreeData`（import `SysMenuNode`）。

- [ ] **Step 2: 实现 Drawer**

结构对齐 `RoleFormDrawer` 菜单区 + 管理员 `Select`：

- Props: `open`, `tenant`, `onClose`, `onSaved`
- State: `checkedKeys`, `expandAll`, `checkStrictly`, `menuTree`
- `useEffect` 打开时 `Promise.all([getTenantPermissions, getTenantAdmins, listTenantUsers, listTenantPermissionMenuTree()])`
- 表单：`menu_ids` 来自 `checkedKeys`；`admin_user_ids: string[]`
- 保存：`putTenantPermissions` + `putTenantAdmins`
- Drawer `width={520}`，`classNames={{ body: 'minerva-scrollbar-styled' }}`
- footer 按钮风格对齐 `RoleFormDrawer`（Cancel / Save 按钮，非 Typography.Link）

- [ ] **Step 3: 管理员 Select**

```tsx
<Select
  mode="multiple"
  showSearch
  allowClear
  optionFilterProp="label"
  placeholder={t('permissions.adminsPlaceholder')}
  options={userOptions}
/>
```

`userOptions` 合并：API 返回成员 + 已选但不在成员中的 orphan 项。

---

## Task 11: `TenantsPage.tsx` 操作列

**Files:**
- Modify: `frontend/src/features/settings/tenants/TenantsPage.tsx`

- [ ] **Step 1: 调整操作列顺序与列宽**

`columns` actions `render` 内 `Space` 顺序：

1. `EditOutlined` — `openEdit`
2. `ApartmentOutlined` — `openWorkspaces`
3. `SafetyCertificateOutlined` — `openPermissions`
4. `DeleteOutlined` + `Popconfirm` — `handleDelete`

`width: 140`。

- [ ] **Step 2: 替换 Drawer import**

`TenantEntitlementDrawer` → `TenantPermissionDrawer`；state 变量 `entitlementOpen` 可重命名为 `permissionOpen`（可选）。

---

## Task 12: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 新增 `permissions.*` 键**

| Key | zh-CN | en |
|-----|-------|-----|
| `permissions.drawerTitle` | 租户授权 — {{name}} | Tenant permissions — {{name}} |
| `permissions.menuLabel` | 菜单权限 | Menu permissions |
| `permissions.adminsLabel` | 租户管理员 | Tenant administrators |
| `permissions.adminsHint` | 从该租户成员中选择一名或多名管理员 | Select one or more administrators from tenant members |
| `permissions.adminsPlaceholder` | 选择租户管理员 | Select tenant administrators |
| `permissions.noTenantUsers` | 该租户暂无成员 | No members in this tenant |
| `permissions.adminOrphanLabel` | {{id}}（已不在租户） | {{id}} (no longer in tenant) |
| `permissions.saved` | 授权已保存 | Permissions saved |
| `permissions.expandCollapse` | 展开/折叠 | Expand/Collapse |
| `permissions.selectAll` | 全选 | Select all |
| `permissions.parentChildLink` | 父子联动 | Parent-child link |

- [ ] **Step 2: 删除未使用的 `entitlements.feature*` 键**（保留 `tenants.entitlements` 作操作列 Tooltip 亦可）

---

## Task 13: 规格文档回填

**Files:**
- Modify: `docs/superpowers/specs/2026-07-01-tenant-page-ux-design.md`（`状态` → 已实现）
- Modify: `docs/superpowers/specs/2026-07-01-unified-permission-gateway-design.md` §3.5 加注「已由 tenant-page-ux spec 替代」

- [ ] **Step 1: 更新 spec 状态与修订记录**

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| 操作列删除置后 | Task 11 |
| `sys_tenant_permission` 表迁移 | Task 1 |
| ORM 重命名 | Task 2 |
| `/permissions` API | Task 6 |
| `GET /users` API | Task 6 |
| menu→feature 推导 | Task 3, 4 |
| 侧栏交集 | Task 7 |
| 全量菜单 Tree 授权 | Task 10 |
| 管理员多选下拉 | Task 10 |
| i18n | Task 12 |
| 测试 | Task 3, 8 |
| spec 回填 | Task 13 |

---

## Manual Verification

1. 以超管登录 → 租户管理 → 操作列顺序正确，删除在最后。
2. 打开授权抽屉 → 菜单 Tree 与角色页一致（全选/展开/父子联动）。
3. 取消勾选 `sub-dataset` 保存 → 租户成员访问 dataset API 403。
4. 租户管理员多选保存回显；侧栏仅显示角色∩租户菜单。
5. 应用 SQL patch 后旧 `feature_code` 数据正确映射为 `menu_id`。
