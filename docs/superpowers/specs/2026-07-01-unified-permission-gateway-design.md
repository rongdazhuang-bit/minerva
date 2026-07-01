# 统一权限网关（RBAC + ABAC 混合 + 独立授权表）设计说明

**日期**：2026-07-01  
**状态**：已实现（P0–P3 + 审查差距修复，2026-07-01）  
**范围**：引入独立授权表、统一 `PermissionGateway`、身份层 `owner` 合并为 `admin`、`sys_role` 改为 tenant 作用域；超管租户功能开通与租户管理员授权链；JWT/前端权限对齐。  
**依赖**：
- [2026-06-10-menu-management-design.md](./2026-06-10-menu-management-design.md)（`sys_menu`、侧栏、perms）
- [2026-06-11-role-management-design.md](./2026-06-11-role-management-design.md)（现有 `sys_role` / `sys_role_menu`，迁移源）
- [2026-06-11-user-management-design.md](./2026-06-11-user-management-design.md)（`sys_user_role`、成员管理）
- [2026-06-11-tenant-management-design.md](./2026-06-11-tenant-management-design.md)（租户 CRUD、超管鉴权）
- [2026-06-12-user-form-membership-tenant-design.md](./2026-06-12-user-form-membership-tenant-design.md)（capabilities、超管旁路，将被网关收敛）

**Supersede 部分**：上述 spec 中关于 `MembershipRole.owner`、分散 `is_super_admin_user` 旁路、`require_workspace_owner_or_admin` 作为唯一写鉴权方式的约定；已在相关 spec 增加交叉引用（2026-07-01）。

**包路径说明**：Python 包名为 `app.sys`；网关与身份域使用 `app.core.security.*`、`app.core.domain.identity.*` 等完整限定导入。

---

## 1. 目标与成功标准

### 1.1 产品决策（已确认）

| 项 | 决策 |
|------|------|
| 架构方案 | **方案 C**：RBAC + ABAC 混合，**独立授权表** + 统一 Permission Gateway |
| 平台超管 | `sys_user.is_super_admin = true` → **全平台数据 + 全菜单 + 全 API**；忽略 tenant entitlement |
| 数据范围 | 非超管以 **workspace** 为数据隔离边界；workspace `admin` 可管理本 workspace 运维数据 |
| workspace 身份 | `sys_workspace_user.role` 仅 **`admin` / `member`**；删除 `owner`，原 `owner` 迁移为 `admin`；新建默认 `member` |
| tenant 身份 | `sys_tenant_user.role` 仅 **`admin` / `member`**；删除 `owner`；**租户管理员权威来源为 grant 表**（见 §3.2） |
| 超管 → 租户 | **`sys_tenant_entitlement`**：为租户开通/关闭功能模块；**`sys_user_grant(tenant_admin)`**：指定租户管理员 |
| 租户管理员 → 成员 | 在本 tenant 内：**成员 CRUD**、**`sys_user_grant(role)`**、**`sys_role` CRUD** |
| `sys_role` 作用域 | **tenant 级**；`tenant_id` NOT NULL；`workspace_id` **NULLABLE**（NULL = tenant 内通用角色） |
| 权限目录 | 新建 **`sys_permission`**；长期由 **`sys_role_permission`** 替代 `sys_role_menu` |
| 用户角色绑定 | 新建 **`sys_user_grant`**；迁移并替代 `sys_user_role` |
| 外键 | **禁止**；关联 UUID + 索引，删除在应用层（minerva-conventions） |

### 1.2 身份 vs 授权分离

| 层 | 表/字段 | 职责 |
|----|---------|------|
| **身份（Membership）** | `sys_user.is_super_admin`、`sys_tenant_user`、`sys_workspace_user` | 用户属于哪里；workspace 数据范围 tier（admin/member） |
| **授权 RBAC** | `sys_permission`、`sys_role`、`sys_role_permission`、`sys_user_grant(grant_type=role)` | 功能权限码（菜单/API） |
| **授权 ABAC** | `sys_user_grant` 的 `scope_*`、`sys_tenant_entitlement` | 按 tenant/workspace/功能模块限定生效范围 |
| **网关** | `PermissionGateway.authorize()` | 统一判定入口 |

### 1.3 成功标准

- 超管：无 workspace membership 可登录；跨 tenant/workspace API 200；侧栏与按钮权限全量；不受 entitlement 限制。
- 租户未开通某 `feature_code`：该 tenant 内所有非超管用户访问对应模块 API **403**。
- 租户管理员（`sys_user_grant.tenant_admin`）：可管理本 tenant 成员、角色、grant；不可管理其他 tenant。
- workspace `admin`：可管理本 workspace 业务与配置数据；不可授予 `tenant_admin`；不可跨 workspace。
- workspace `member`：仅 effective permissions 允许的操作；无 grant 时最小权限。
- 原 `owner` 用户迁移后行为与 `admin` 一致。
- 所有新鉴权经 `PermissionGateway`；旧 deps 在 P3 前可薄封装转发，P3 后删除直读 `is_super_admin_user` 的散落逻辑。

---

## 2. 身份层变更

### 2.1 `MembershipRole` 枚举

**目标值**（tenant / workspace 共用逻辑枚举，PostgreSQL 各用独立 enum 类型名不变）：

- `admin`
- `member`

**删除**：`owner`

### 2.2 数据迁移

```sql
-- workspace
UPDATE sys_workspace_user SET role = 'admin' WHERE role = 'owner';

-- tenant
UPDATE sys_tenant_user SET role = 'admin' WHERE role = 'owner';
```

**枚举重建**（patch 中实现）：新建仅含 `admin`/`member` 的 enum → 列改型 → 删除旧 enum。过渡期（可选 1 个版本）应用层将读到的 `owner` 视为 `admin` 并打 deprecation 日志。

### 2.3 注册与默认

- `register_user`：创建者 `sys_tenant_user.role = admin`、`sys_workspace_user.role = admin`（原 owner 语义）。
- 超管新建成员：`sys_workspace_user.role` 默认 **`member`**（与现网一致）。
- `sys_tenant_user` 存在仅表示「属于 tenant」；**是否 tenant 管理员**由 `sys_user_grant` 判定，不单独依赖 `sys_tenant_user.role = admin`（该字段可保留用于兼容展示，但 **授权以 grant 为准**）。

### 2.4 登录与 JWT

**问题**：现网超管无 membership 无法登录（`authenticate_user` 要求 `sys_workspace_user`）。

**调整**：

- 超管登录：若无 membership，选取平台首个 `status=true` 的 tenant/workspace 作为 JWT 上下文，或专用「平台上下文」workspace（实现时二选一，**推荐**首个可用 tenant/workspace + 网关旁路 membership）。
- `_issue_tokens`：超管无 membership 时不抛 `auth.no_workspace_membership`。
- `require_workspace_member` / 网关 `require_data_scope`：超管旁路。

**JWT access payload 扩展**：

| claim | 说明 |
|-------|------|
| `sub` | user id |
| `tid` | tenant id |
| `wid` | workspace id |
| `sa` | `bool`，`is_super_admin` |
| `trole` | `admin` \| `member` |
| `wrole` | `admin` \| `member` |
| `type` | `access` |

---

## 3. 新建与改造表

### 3.1 约定

- 主键 UUID；禁止外键；逻辑引用在 COMMENT / docstring 说明。
- 同步 `backend/sql/schema_postgresql.sql`；增量 patch：`backend/sql/patches/2026-07-01-unified-permission-gateway.sql`（可按 P0–P3 拆分子 patch）。
- ORM 注册于 `app/core/infrastructure/db/bootstrap.py`。

### 3.2 `sys_permission`（新建，全局权限目录）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | |
| `perm_code` | VARCHAR(128) | NOT NULL，**全局唯一** | 如 `dataset:read`、`sys:user:add`、`feature:agent` |
| `perm_name` | VARCHAR(128) | NOT NULL | 显示名 |
| `perm_type` | VARCHAR(16) | NOT NULL | `menu` / `api` / `data` / `feature` |
| `resource_pattern` | VARCHAR(256) | NULL | ABAC 资源模式，如 `workspace:*` |
| `menu_id` | UUID | NULL，索引 | 逻辑引用 `sys_menu.id`（menu 型权限同步来源） |
| `status` | BOOLEAN | NOT NULL DEFAULT true | |
| `remark` | VARCHAR(500) | NULL | |
| `create_at` | TIMESTAMPTZ | NULL DEFAULT now() | |
| `update_at` | TIMESTAMPTZ | NULL | |

**索引**：`uq_sys_permission_perm_code` UNIQUE ON (`perm_code`)；`ix_sys_permission_perm_type`；`ix_sys_permission_menu_id`。

**种子**：自 `sys_menu` 导入 M/C/F；自各模块整理 API 权限码；feature 类见 §3.5。

### 3.3 `sys_role`（改造）

| 字段 | 变更 | 说明 |
|------|------|------|
| `tenant_id` | **新增** NOT NULL | 角色归属 tenant |
| `workspace_id` | **改为 NULLABLE** | NULL = tenant 内所有 workspace 可用；非 NULL = 仅该 workspace |
| `role_key` | 唯一约束变更 | **`UNIQUE (tenant_id, role_key)`**（替代原 workspace 内唯一） |
| 其余 | 保留 | `role_name`、`role_sort`、`status`、`remark`、时间字段 |

**迁移**：现有行的 `tenant_id` 由 `sys_workspaces.tenant_id` 回填；`workspace_id` 保持原值。

### 3.4 `sys_role_permission`（新建）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | PK |
| `role_id` | UUID | NOT NULL，索引 → `sys_role.id` |
| `permission_id` | UUID | NOT NULL，索引 → `sys_permission.id` |

**索引**：`uq_sys_role_permission_role_perm` UNIQUE ON (`role_id`, `permission_id`)。

**与 `sys_role_menu` 关系**：P0–P2 双读；P3 从 `sys_role_menu` 迁移后废弃 `sys_role_menu` 表（应用层停止写入）。

### 3.5 `sys_tenant_entitlement`（新建，超管 → 租户 ABAC）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | PK |
| `tenant_id` | UUID | NOT NULL，索引 |
| `feature_code` | VARCHAR(64) | NOT NULL，与 `sys_permission.perm_code` 中 `feature:*` 对齐 |
| `enabled` | BOOLEAN | NOT NULL DEFAULT true |
| `granted_by_user_id` | UUID | NOT NULL |
| `create_at` | TIMESTAMPTZ | |
| `update_at` | TIMESTAMPTZ | |

**索引**：`uq_sys_tenant_entitlement_tenant_feature` UNIQUE ON (`tenant_id`, `feature_code`)。

**首期 feature_code 清单**（可扩展）：

| feature_code | 模块 |
|--------------|------|
| `feature:agent` | Agent / MCP / Memory |
| `feature:dataset` | 知识库 |
| `feature:ocr` | 文件 OCR |
| `feature:skills` | Agent Skills |
| `feature:translate` | 翻译 |
| `feature:rules` | 规则 |
| `feature:file_storage` | 文件存储 |

未配置 entitlement 的 feature：**默认关闭**（非超管 403）。超管不受限。

### 3.6 `sys_user_grant`（新建，核心授权表）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | PK |
| `user_id` | UUID | NOT NULL，索引 |
| `grant_type` | VARCHAR(32) | NOT NULL：`role` / `direct_permission` / `tenant_admin` |
| `role_id` | UUID | NULL → `sys_role.id` |
| `permission_id` | UUID | NULL → `sys_permission.id` |
| `scope_type` | VARCHAR(16) | NOT NULL：`platform` / `tenant` / `workspace` |
| `scope_id` | UUID | NULL；platform 级为 NULL；tenant/workspace 级为对应 id |
| `granted_by_user_id` | UUID | NOT NULL |
| `status` | BOOLEAN | NOT NULL DEFAULT true |
| `create_at` | TIMESTAMPTZ | |
| `update_at` | TIMESTAMPTZ | |

**索引**：

- `ix_sys_user_grant_user_scope` ON (`user_id`, `scope_type`, `scope_id`)
- `ix_sys_user_grant_scope_type_id` ON (`scope_type`, `scope_id`)
- `uq_sys_user_grant_user_role_scope` UNIQUE ON (`user_id`, `grant_type`, `role_id`, `scope_type`, `scope_id`) WHERE `grant_type = 'role'`（partial unique，实现方式以 patch 为准）

**grant_type 规则**：

| grant_type | 写入者 | scope | 隐含权限 |
|------------|--------|-------|----------|
| `tenant_admin` | **仅超管** | `scope_type=tenant`, `scope_id=tenant_id` | `tenant:member:manage`、`tenant:role:manage` |
| `role` | tenant admin（本 tenant） | tenant 或 workspace | 该 role 的 `sys_role_permission` 并集 |
| `direct_permission` | tenant admin（本 tenant，可选能力） | tenant 或 workspace | 单条 `perm_code` |

**校验（service 层）**：

- `grant_type=role` → `role.tenant_id` 与 `scope` 一致；若 `scope_type=workspace` 则 role 的 `workspace_id` 为 NULL 或等于 `scope_id`。
- `grant_type=tenant_admin` → 同一 `(user_id, scope_id)` 至多一条 `status=true`。
- 撤销 tenant admin：`status=false` 或 DELETE 行。

### 3.7 废弃表（P3）

| 表 | 处理 |
|----|------|
| `sys_user_role` | 数据迁入 `sys_user_grant` 后删除 |
| `sys_role_menu` | 数据迁入 `sys_role_permission` 后删除 |

---

## 4. Permission Gateway

### 4.1 模块结构

```text
backend/app/core/security/
  permission_context.py       # PermissionContext  dataclass
  permission_gateway.py       # PermissionGateway.authorize / check
  permission_resolver.py      # resolve_effective_permissions / menus / features
  permission_codes.py         # 常量与 feature 清单
  deps.py                     # require_permission, require_data_scope, require_super_admin
```

### 4.2 `PermissionContext`（每请求构建）

```python
@dataclass(frozen=True)
class PermissionContext:
    user_id: UUID
    is_super_admin: bool
    tenant_id: UUID | None
    workspace_id: UUID | None
    tenant_role: MembershipRole | None      # membership，非 grant
    workspace_role: MembershipRole | None
    is_tenant_admin: bool                   # 来自 sys_user_grant(tenant_admin)
    tenant_features: frozenset[str]         # enabled entitlement feature_code
    permissions: frozenset[str]             # effective perm_code
    menu_ids: frozenset[UUID]               # 侧栏用
```

构建来源：JWT claims + DB（grants、roles、entitlements、membership）。可请求级缓存。

### 4.3 判定流水线

```text
1. is_super_admin → ALLOW（跳过 2–5）

2. ABAC 功能门禁
   action.feature_code 非空 且 feature_code ∉ tenant_features → DENY

3. ABAC 数据范围
   - action 绑定 resource.workspace_id：
     - 非超管：须 sys_workspace_user 存在
     - workspace 须属于 JWT tenant（查 sys_workspaces.tenant_id）
   - action 绑定 resource.tenant_id：非超管须 sys_tenant_user 存在

4. ABAC 管理动作
   - platform:* → 仅超管
   - tenant:* → 超管 或 is_tenant_admin（同 tenant）
   - workspace:manage → 超管 或 workspace_role=admin（同 workspace）

5. RBAC 功能权限
   action.perm_code ∈ ctx.permissions → ALLOW
   tenant_admin 隐含 tenant:member:manage、tenant:role:manage

6. DENY → 403 auth.forbidden
```

### 4.4 FastAPI 依赖映射

| 现有 | 迁移目标 |
|------|----------|
| `require_super_admin` | `require_permission(...)` 或 `require_super_admin()` |
| `require_any_workspace_member` | `require_authenticated` + 非超管时须至少一条 workspace membership（读字典等） |
| `require_workspace_member` | `require_data_scope(workspace_id)` |
| `require_workspace_owner_or_admin` | `require_permission("workspace:manage", workspace_id=...)` |
| `require_tenant_owner_or_admin` | `require_tenant_admin()` 或 `require_permission("tenant:skills:manage")` |
| `require_workspace_manager_or_super_admin` | `require_permission("tenant:member:manage")` 或 workspace admin |
| `menu_service.list_nav_tree_for_user` | `permission_resolver.resolve_nav_tree(ctx)` |

### 4.5 侧栏与按钮权限

| 主体 | 侧栏 M/C | 按钮 F / API |
|------|----------|--------------|
| 超管 | 全量 `sys_menu`（visible+status） | 全量 |
| 非超管 | `permissions` 中 `perm_type=menu` 对应 menu_id 并集 + 祖先目录 | `permissions` 中 `perm_code`；前端 `hasPerm(code)` |

**管理类菜单**（设置、用户、角色、租户）：非超管需对应 `tenant:*` 或 `workspace:manage` 权限码，不单靠 membership。

---

## 5. API 设计

### 5.1 新增

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/auth/me/authorization` | 已登录 | 返回 §4.2 有效权限摘要（供前端） |
| GET | `/sys/permissions` | 超管 | 权限目录分页（管理用） |
| GET | `/sys/tenants/{tenant_id}/entitlements` | 超管 | 租户已开通功能列表 |
| PUT | `/sys/tenants/{tenant_id}/entitlements` | 超管 | 全量替换 entitlement |
| GET | `/sys/tenants/{tenant_id}/admins` | 超管 | tenant_admin grant 列表 |
| PUT | `/sys/tenants/{tenant_id}/admins` | 超管 | 全量替换 tenant 管理员 user_ids |
| GET | `/sys/tenants/{tenant_id}/grants` | tenant admin | 本 tenant grant 列表（分页/筛选） |
| POST | `/sys/tenants/{tenant_id}/grants` | tenant admin | 创建 role/direct grant |
| DELETE | `/sys/tenants/{tenant_id}/grants/{grant_id}` | tenant admin | 撤销 grant |

### 5.2 调整现有 API 鉴权

| 模块 | 调整 |
|------|------|
| `/sys/tenants/*` | 保持超管；entitlement/admins 子资源见上 |
| `/workspaces/{wid}/users/*` 写 | tenant admin 或 workspace admin 或超管（经网关） |
| `/workspaces/{wid}/roles/*` 写 | **tenant admin**（本 tenant）或超管 |
| `/sys/menus/*` 写 | 超管或 tenant admin（可配置，**默认超管 + tenant admin**） |
| 各业务模块 `/{wid}/*` | `require_data_scope` + 对应 `feature:*` entitlement |

### 5.3 `GET /auth/me/authorization` 响应示例

```json
{
  "is_super_admin": false,
  "tenant_id": "uuid",
  "workspace_id": "uuid",
  "workspace_role": "member",
  "tenant_role": "member",
  "is_tenant_admin": true,
  "tenant_features": ["feature:agent", "feature:dataset"],
  "permissions": ["dataset:read", "tenant:member:manage", "tenant:role:manage"],
  "menu_paths": ["/app/datasets", "/app/settings/users"]
}
```

---

## 6. 前端

### 6.1 `AuthContext` 扩展

| 字段/方法 | 说明 |
|-----------|------|
| `isSuperAdmin` | JWT `sa` 或 `/auth/me/authorization` |
| `isTenantAdmin` | authorization API |
| `isWorkspaceAdmin` | JWT `wrole === 'admin'` |
| `tenantFeatures` | `Set<string>` |
| `hasPerm(code)` | 超管恒 true；否则 `permissions.has(code)` |
| 废弃 | `isWorkspaceManager` → 别名 `isWorkspaceAdmin`（一版兼容后删除） |
| 废弃 | `canManageTenantSkills` → `hasPerm('tenant:skills:manage')` 或 feature + tenant admin |

登录后调用 `GET /auth/me/authorization` 填充 permissions（React Query 缓存）。

### 6.2 UI 变更

| 页面 | 变更 |
|------|------|
| `TenantsPage` | 超管：功能开通（entitlement 多选）+ 租户管理员指定 |
| `RolesPage` | 鉴权改为 tenant admin；角色列表按 `tenant_id`（当前 JWT tenant） |
| `UsersPage` | tenant admin 可管理 tenant 内成员；分配角色走 grant API |
| `AppLayout` / 侧栏 | 仍 `GET /sys/menus/nav`（后端走 resolver） |
| 按钮 | 新增 `usePerm()` / `<PermGuard perm="...">`（F 类型） |

### 6.3 i18n

- 移除「所有者 / owner」文案，统一「管理员 / admin」。
- 新增 `permissions.*`、`entitlements.*`、`tenantAdmins.*`。

---

## 7. 实现分期

| 阶段 | 交付 |
|------|------|
| **P0** | 建表（permission、grant、entitlement）；owner→admin 迁移；`PermissionGateway` + deps 薄封装；超管登录/membership 旁路；JWT `sa` |
| **P1** | entitlement + tenant_admin API；TenantsPage 扩展；feature 门禁接入 1–2 个模块验证 |
| **P2** | `sys_user_grant` 替代 `sys_user_role`；tenant admin 用户/角色/grant 管理 UI；`/auth/me/authorization` |
| **P3** | `sys_role` tenant 作用域迁移；`sys_role_permission` 替代 `sys_role_menu`；删除旧表；移除双读与 scattered `is_super_admin_user` |

---

## 8. 测试与验收

### 8.1 后端

- 超管：无 membership 登录成功；跨 workspace CRUD 200。
- entitlement 关闭 `feature:dataset` → tenant 内 dataset API 403；超管 200。
- tenant admin：可 POST grant；不可 PUT 其他 tenant entitlement。
- workspace admin：本 workspace 200；其他 workspace 404/403。
- member：无 grant 时仅最小只读（按角色配置）。
- owner 迁移后 API 行为与 admin 一致。
- grant 校验：role tenant 与 scope 不一致 → 400。

### 8.2 前端

- TenantsPage entitlement + tenant admin 保存回显。
- tenant admin 可见用户/角色管理；member 不可见写操作。
- `hasPerm` 控制按钮；超管全部可见。
- 侧栏与 `permissions` 一致。

---

## 9. 范围外（本期不做）

| 项 | 说明 |
|----|------|
| RuoYi 式部门/本人数据范围 | 仍以 workspace 为界；department 仅展示字段 |
| 权限变更审计日志独立表 | 可后续用 `granted_by` + 应用日志 |
| 多 tenant 同时 active 的 JWT | 仍单 `tid`/`wid` 上下文；切换 workspace 后续独立 spec |
| SSO / 外部 IdP | 不在本期 |

---

## 10. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-07-01 | 初稿：brainstorming 确认方案 C；身份 owner 合并；tenant 作用域 role；独立 grant/entitlement；统一网关 |
| 2026-07-01 | 用户确认 §1–§4 及 tenant 作用域 sys_role |

---

## 11. 实现对照

| spec 条目 | 计划代码位置 | 状态 |
|-----------|--------------|------|
| PermissionGateway | `backend/app/core/security/permission_gateway.py` | 已实现 |
| sys_permission ORM | `backend/app/core/domain/authorization/models.py` | 已实现 |
| sys_user_grant | 同上 | 已实现 |
| sys_tenant_entitlement | 同上 | 已实现 |
| owner→admin patch | `backend/sql/patches/2026-07-01-unified-permission-gateway-p0.sql` | 已实现 |
| grant 双写 / 读切换 | `backend/sql/patches/2026-07-01-unified-permission-gateway-p2.sql` + user/grant service | 已实现 |
| sys_role tenant 作用域 | `backend/sql/patches/2026-07-01-unified-permission-gateway-p3.sql` | 已实现 |
| sys_role_permission 替代 sys_role_menu | P3 patch + `role/infrastructure/repository.py` | 已实现 |
| 废弃 sys_user_role / sys_role_menu | P3 patch `DROP TABLE` | 已实现 |
| GET /auth/me/authorization | `backend/app/core/api/routers/auth.py` | 已实现 |
| TenantsPage entitlement UI | `frontend/src/features/settings/tenants/` | 已实现 |
| AuthContext hasPerm | `frontend/src/app/AuthContext.tsx` | 已实现 |
| Grant API | `backend/app/sys/tenant/api/router.py` | 已实现 |
| GET /sys/permissions | `backend/app/sys/permission/api/router.py` | 已实现 |
| Feature 门禁（各业务模块） | `backend/app/core/security/permission_deps.py` + 各模块 `api/deps.py` | 已实现 |
| usePerm / PermGuard | `frontend/src/components/PermGuard.tsx` | 已实现 |
