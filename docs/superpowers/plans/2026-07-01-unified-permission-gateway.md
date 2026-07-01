# 统一权限网关（RBAC + ABAC）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现方案 C：独立授权表 + `PermissionGateway` + 身份 owner 合并 + 超管/租户管理员授权链 + 前端权限对齐。

**Architecture:** 身份（membership）与授权（grant/entitlement/permission）分离；所有鉴权经 `PermissionGateway.authorize()`；P0–P2 与旧 `sys_role_menu`/`sys_user_role` 双读；P3 完成 tenant 作用域 role 迁移并废弃旧表。

**Tech Stack:** FastAPI, SQLAlchemy async, PostgreSQL SQL patch, pytest, React, TanStack Query, Ant Design

**Spec:** `docs/superpowers/specs/2026-07-01-unified-permission-gateway-design.md`

---

## File Map

| 文件 | 职责 |
|------|------|
| `backend/sql/patches/2026-07-01-unified-permission-gateway-p0.sql` | P0：新表 + owner→admin 枚举迁移 |
| `backend/sql/tables/sys_permission.sql` 等 | 新表 DDL 片段 |
| `backend/sql/schema_postgresql.sql` | 同步全库定义 |
| `backend/app/core/domain/authorization/models.py` | `SysPermission`、`SysRolePermission`、`SysTenantEntitlement`、`SysUserGrant` ORM |
| `backend/app/core/domain/authorization/repository.py` | grant/entitlement/permission 查询 |
| `backend/app/core/security/permission_codes.py` | 权限码与 feature 常量 |
| `backend/app/core/security/permission_context.py` | `PermissionContext` |
| `backend/app/core/security/permission_resolver.py` | 解析 effective permissions / nav |
| `backend/app/core/security/permission_gateway.py` | `authorize()` 流水线 |
| `backend/app/core/security/permission_deps.py` | FastAPI `require_permission` 等 |
| `backend/app/core/domain/identity/models.py` | `MembershipRole` 去 owner |
| `backend/app/core/infrastructure/security/jwt_tokens.py` | JWT `sa` claim |
| `backend/app/core/api/routers/auth.py` | 超管登录旁路 + `/auth/me/authorization` |
| `backend/app/core/api/deps.py` | 薄封装转发 gateway |
| `backend/app/sys/tenant/api/router.py` | entitlement + admins 子资源（P1） |
| `backend/app/sys/tenant/service/entitlement_service.py` | entitlement CRUD（P1） |
| `backend/tests/test_permission_gateway.py` | 网关单元测试 |
| `backend/tests/test_auth_super_admin.py` | 超管登录集成测试 |
| `frontend/src/app/AuthContext.tsx` | `isSuperAdmin` / `hasPerm` |
| `frontend/src/api/auth.ts` | authorization API |
| `frontend/src/features/settings/tenants/TenantsPage.tsx` | entitlement + tenant admins UI（P1） |

---

## Phase P0 — 基础表 + 网关 + 超管旁路

### Task 1: SQL patch 与 schema（P0 新表 + owner 迁移）

**Files:**
- Create: `backend/sql/patches/2026-07-01-unified-permission-gateway-p0.sql`
- Create: `backend/sql/tables/sys_permission.sql`
- Create: `backend/sql/tables/sys_role_permission.sql`
- Create: `backend/sql/tables/sys_tenant_entitlement.sql`
- Create: `backend/sql/tables/sys_user_grant.sql`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 编写 P0 patch**

`backend/sql/patches/2026-07-01-unified-permission-gateway-p0.sql` 含：
1. `UPDATE sys_workspace_user/sys_tenant_user SET role='admin' WHERE role='owner'`
2. 重建 `tenant_role` / `workspace_role` 枚举为 `('admin','member')`
3. `CREATE TABLE sys_permission`、`sys_role_permission`、`sys_tenant_entitlement`、`sys_user_grant`（无 FK）

- [ ] **Step 2: 同步 schema_postgresql.sql**

- [ ] **Step 3: 本地验证 patch 语法**（可读性检查；CI/DB 环境 apply 由部署流程负责）

---

### Task 2: Authorization ORM + bootstrap

**Files:**
- Create: `backend/app/core/domain/authorization/__init__.py`
- Create: `backend/app/core/domain/authorization/models.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`
- Modify: `backend/app/core/domain/identity/models.py`

- [ ] **Step 1: 新建 ORM**

`models.py` 定义四表 ORM，字段对齐 spec §3.2–§3.6；每类 docstring。

- [ ] **Step 2: MembershipRole 删除 owner**

```python
class MembershipRole(str, enum.Enum):
    """Tenant/workspace authorization role bucket."""

    admin = "admin"
    member = "member"
```

`register_user` 中 `MembershipRole.owner` → `MembershipRole.admin`。

- [ ] **Step 3: bootstrap 注册**

```python
import app.core.domain.authorization.models  # noqa: F401
```

---

### Task 3: permission_codes + PermissionContext

**Files:**
- Create: `backend/app/core/security/permission_codes.py`
- Create: `backend/app/core/security/permission_context.py`

- [ ] **Step 1: 常量**

```python
TENANT_MEMBER_MANAGE = "tenant:member:manage"
TENANT_ROLE_MANAGE = "tenant:role:manage"
WORKSPACE_MANAGE = "workspace:manage"
PLATFORM_TENANT_MANAGE = "platform:tenant:manage"

FEATURE_CODES = frozenset({
    "feature:agent",
    "feature:dataset",
    "feature:ocr",
    "feature:skills",
    "feature:translate",
    "feature:rules",
    "feature:file_storage",
})

TENANT_ADMIN_IMPLICIT_PERMS = frozenset({TENANT_MEMBER_MANAGE, TENANT_ROLE_MANAGE})
```

- [ ] **Step 2: PermissionContext dataclass**（对齐 spec §4.2）

---

### Task 4: permission_resolver + repository

**Files:**
- Create: `backend/app/core/domain/authorization/repository.py`
- Create: `backend/app/core/security/permission_resolver.py`

- [ ] **Step 1: repository**

函数：
- `load_tenant_entitlements(session, tenant_id) -> list[str]`
- `load_user_grants(session, user_id) -> list[SysUserGrant]`
- `is_tenant_admin_grant(session, user_id, tenant_id) -> bool`
- `load_role_permission_codes(session, role_ids) -> set[str]`
- `load_menu_permissions_dual(session, role_ids) -> set[UUID]`（双读 role_menu + role_permission）

- [ ] **Step 2: build_permission_context(session, user, jwt_payload) -> PermissionContext**

- [ ] **Step 3: resolve_nav_menu_ids(ctx) -> set[UUID]`**（超管全量；非超管 dual-read）

---

### Task 5: PermissionGateway + deps

**Files:**
- Create: `backend/app/core/security/permission_gateway.py`
- Create: `backend/app/core/security/permission_deps.py`
- Modify: `backend/app/core/api/deps.py`

- [ ] **Step 1: PermissionAction dataclass**

```python
@dataclass(frozen=True)
class PermissionAction:
    perm_code: str | None = None
    feature_code: str | None = None
    workspace_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    require_workspace_manage: bool = False
    require_tenant_admin: bool = False
    require_super_admin: bool = False
```

- [ ] **Step 2: authorize(ctx, action) -> None | raises AppError**

实现 spec §4.3 六步流水线。

- [ ] **Step 3: FastAPI deps**

```python
async def require_data_scope(workspace_id: UUID, ...) -> UUID
async def require_permission(perm_code: str, ...) -> PermissionContext
async def get_permission_context(...) -> PermissionContext
```

- [ ] **Step 4: 薄封装现有 deps**

`require_workspace_member` → 调 `require_data_scope`；`require_workspace_owner_or_admin` → `require_permission(WORKSPACE_MANAGE)`；保留函数签名避免全库一次性改路由。

---

### Task 6: JWT `sa` + 超管登录旁路

**Files:**
- Modify: `backend/app/core/infrastructure/security/jwt_tokens.py`
- Modify: `backend/app/core/api/routers/auth.py`
- Modify: `backend/app/core/domain/identity/services.py`

- [ ] **Step 1: create_access_token 增加 is_super_admin 参数 → payload `sa`**

- [ ] **Step 2: authenticate_user 超管无 membership 时选首个 tenant/workspace**

```python
if first is None and user.is_super_admin:
    ws_row = await session.execute(
        select(Workspace, Tenant)
        .select_from(Workspace)
        .join(Tenant, Tenant.id == Workspace.tenant_id)
        .where(Tenant.status.is_(True), Workspace.status.is_(True))
        .limit(1)
    )
    first = ws_row.first()
```

- [ ] **Step 3: _issue_tokens 超管无 wrole 时不 401**（wrole/trole 可为 None）

- [ ] **Step 4: refresh 同步超管旁路逻辑**

---

### Task 7: menu_service 接入 resolver

**Files:**
- Modify: `backend/app/sys/menu/service/menu_service.py`

- [ ] **Step 1: list_nav_tree_for_user 改为调用 permission_resolver.resolve_nav_tree**

保留 `is_super_admin_user` 短路或统一 ctx。

---

### Task 8: P0 测试

**Files:**
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_permission_gateway.py`
- Create: `backend/tests/test_auth_super_admin.py`

- [ ] **Step 1: conftest 最小 fixture**（内存 SQLite 或 skip-if-no-db 按项目惯例）

- [ ] **Step 2: test_super_admin_bypasses_data_scope**

- [ ] **Step 3: test_member_denied_workspace_manage**

- [ ] **Step 4: test_tenant_admin_implicit_perms**

Run: `cd backend && pytest tests/test_permission_gateway.py -v`

- [ ] **Step 5: Commit P0**

```bash
git add backend/ docs/superpowers/plans/2026-07-01-unified-permission-gateway.md
git commit -m "feat(auth): P0 unified permission gateway foundation"
```

---

## Phase P1 — Entitlement + Tenant Admin API + UI

### Task 9: entitlement + tenant admin service/API

**Files:**
- Create: `backend/app/sys/tenant/service/entitlement_service.py`
- Modify: `backend/app/sys/tenant/api/router.py`
- Create: `backend/app/sys/tenant/api/schemas_entitlement.py`

- [ ] **Step 1: GET/PUT `/sys/tenants/{tenant_id}/entitlements`**（require_super_admin）
- [ ] **Step 2: GET/PUT `/sys/tenants/{tenant_id}/admins`**（写 sys_user_grant tenant_admin）
- [ ] **Step 3: 测试 test_tenant_entitlement_api.py**

---

### Task 10: Feature 门禁接入 dataset 模块（验证）

**Files:**
- Modify: `backend/app/dataset/api/router.py`（或 deps 包装）

- [ ] **Step 1: 列表/读接口 require feature:dataset**
- [ ] **Step 2: 测试 entitlement 关闭 → 403**

---

### Task 11: TenantsPage UI

**Files:**
- Modify: `frontend/src/features/settings/tenants/TenantsPage.tsx`
- Create: `frontend/src/api/tenantEntitlements.ts`

- [ ] **Step 1: entitlement 多选 + 保存**
- [ ] **Step 2: tenant admins 用户选择 + 保存**
- [ ] **Step 3: i18n**

- [ ] **Step 4: Commit P1**

---

## Phase P2 — Grant 替代 user_role + Authorization API + 前端

### Task 12: sys_user_grant 双写 + 读切换

**Files:**
- Modify: `backend/app/sys/user/service/user_service.py`
- Modify: `backend/app/sys/user/infrastructure/repository.py`

- [ ] **Step 1: 写 user_role 时同步写 grant**
- [ ] **Step 2: 读角色从 grant 优先**

---

### Task 13: GET /auth/me/authorization

**Files:**
- Modify: `backend/app/core/api/routers/auth.py`
- Create: `frontend/src/api/auth.ts`
- Modify: `frontend/src/app/AuthContext.tsx`

- [ ] **Step 1: 后端 endpoint**
- [ ] **Step 2: 前端登录后拉取 + hasPerm / isSuperAdmin / isTenantAdmin**

---

### Task 14: Tenant admin 用户/角色/grant 管理

**Files:**
- Modify: `backend/app/sys/user/api/deps.py`
- Modify: `backend/app/sys/role/api/router.py`
- Create: `backend/app/sys/tenant/api/grant_router.py`（或合入 tenant router）

- [x] **Step 1: GET/POST/DELETE grants**
- [x] **Step 2: 角色写鉴权改 tenant admin**
- [x] **Step 3: UsersPage / RolesPage 对齐**
- [x] **Step 4: PermissionsPage / GrantsPage + 路由/i18n**

- [ ] **Step 5: Commit P2**

---

## Phase P3 — sys_role tenant 作用域 + 废弃旧表

### Task 15: sys_role 加 tenant_id + 迁移

**Files:**
- Create: `backend/sql/patches/2026-07-01-unified-permission-gateway-p3.sql`
- Modify: `backend/app/sys/role/domain/db/models.py`

- [ ] **Step 1: ADD tenant_id, workspace_id NULLABLE, 唯一约束 (tenant_id, role_key)**
- [ ] **Step 2: 回填 tenant_id from workspace**

---

### Task 16: sys_role_permission 迁移 + 停写 sys_role_menu

- [ ] **Step 1: 从 sys_role_menu 导入 sys_role_permission**
- [ ] **Step 2: role_service 写 role_permission**
- [x] **Step 3: 删除 sys_user_role / sys_role_menu 表（patch）** — `2026-07-01-unified-permission-gateway-p3.sql`

---

### Task 17: 清理散落 is_super_admin + spec 回填

- [x] **Step 1: 删除 `require_tenant_owner_or_admin` / `is_any_tenant_owner_or_admin`**
- [x] **Step 2: `PermGuard` hooks + grant service 测试**
- [ ] **Step 3: 更新 spec §11 实现对照 + 状态「已实现」**
- [ ] **Step 4: Commit P3**

---

## Spec Coverage Self-Check

| Spec § | Plan Task |
|--------|-----------|
| §2 owner→admin | Task 1, 2 |
| §3 新表 | Task 1, 2 |
| §4 Gateway | Task 3–5, 7 |
| §2.4 JWT/登录 | Task 6 |
| §5 entitlement/admins API | Task 9 |
| §5.2 业务门禁 | Task 10 |
| §6 前端 | Task 11, 13, 14 |
| §3.3 sys_role tenant | Task 15 |
| §3.7 废弃旧表 | Task 16 |
| §7 P0–P3 | Phase 分节 |
