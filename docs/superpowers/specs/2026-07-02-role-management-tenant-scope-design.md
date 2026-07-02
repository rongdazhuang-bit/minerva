# 角色管理：租户域 API 与授权优化 — 设计说明

**日期**：2026-07-02  
**状态**：待实现  
**范围**：角色管理 API 从 workspace 路径迁移至租户域；超管/租户管理员在列表筛选与新建/编辑弹窗中按租户 → 工作空间配置角色归属；编辑时 scope 只读。  
**依赖**：
- [2026-06-11-role-management-design.md](./2026-06-11-role-management-design.md)（原 workspace 路由基线，本 spec supersede 其 API 路径与 UI scope 部分）
- [2026-06-12-user-form-membership-tenant-design.md](./2026-06-12-user-form-membership-tenant-design.md)（租户/工作空间级联选择交互参考）
- [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)（`PermissionGateway`、`tenant:role:manage`）

---

## 1. 目标与成功标准

### 1.1 变更摘要

1. **API 迁移（方案 C）**
   - 角色 CRUD 主路由迁至 `/sys/tenants/{tenant_id}/roles`。
   - 超管跨租户列表使用平台级 `GET /sys/roles`。
   - **删除**旧路由 `/workspaces/{workspace_id}/roles/*`（前后端同步）。

2. **列表页 scope 筛选**
   - 超管：可选任意租户 + 任意/全部工作空间；默认「全部租户 / 全部工作空间」。
   - 租户管理员：租户固定为当前租户（不可改）；工作空间可选任意/全部；默认「当前租户 / 全部工作空间」。
   - 普通成员：无 scope 筛选，行为与现网接近（只看有权限的数据）。

3. **新建/编辑弹窗**
   - **新建**：超管可选「租户 → 工作空间」级联；租户管理员租户只读、工作空间必选；角色**仅绑定具体 workspace**（`workspace_id` 必填，非 NULL）。
   - **编辑**：租户 + 工作空间**只读**展示，不可变更 scope。

### 1.2 不在本期

- 租户级通用角色（`workspace_id = NULL`）的新建与列表展示。
- 编辑时迁移角色到其他 workspace。
- 角色 grant 管理 UI（仍走现有 `/sys/tenants/{tid}/grants`）。

### 1.3 成功标准

- 超管可在「全部/全部」默认下浏览跨租户角色列表，并在新建时指定任意租户下的 workspace。
- 租户管理员只能操作本租户角色；访问其他 `tenant_id` 返回 403。
- 新建角色 `workspace_id` 必填且归属路径 `tenant_id`；`role_key` 在 tenant 内唯一（现有约束）。
- 编辑 PATCH 不接受 `tenant_id` / `workspace_id` 变更。
- 旧 workspace 角色路由移除后，前端角色页与用户表单 assignable roles 仍正常工作。

---

## 2. 权限与可见性矩阵

| 操作者 | 列表 scope 筛选 | 新建弹窗 | 编辑弹窗 scope |
|--------|-----------------|----------|----------------|
| **平台超管** (`is_super_admin`) | 租户可选（含「全部」）；工作空间可选（含「全部」） | 租户 → 工作空间级联，workspace 必选 | 只读 |
| **租户管理员** (`tenant_admin` grant) | 租户固定（当前租户）；工作空间可选（含「全部」） | 租户只读；workspace 下拉必选 | 只读 |
| **普通 workspace 成员** | 无 scope 筛选 | 无新建按钮（`tenant:role:manage`） | — |

**写操作鉴权**（新建 dep `require_tenant_role_manager(tenant_id)`）：

1. 超管 → 放行  
2. `is_tenant_admin(user_id, tenant_id)` → 放行  
3. 否则 → 403

**读操作**：超管任意 tenant；租户管理员本 tenant；普通成员可读其可见 workspace 下的角色（详情/列表按 repository 过滤）。

---

## 3. 后端设计

### 3.1 路由一览

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| `GET` | `/sys/roles` | 超管 | 跨租户分页；query: `tenant_id?`, `workspace_id?`, `role_name?`, `status?`, `role_key?`, `page`, `page_size` |
| `GET` | `/sys/tenants/{tenant_id}/roles` | 超管 / 租户管理员 | 租户内分页；query: `workspace_id?` 等 |
| `POST` | `/sys/tenants/{tenant_id}/roles` | 超管 / 租户管理员 | 创建；body 必填 `workspace_id` |
| `GET` | `/sys/tenants/{tenant_id}/roles/{role_id}` | 读权限 | 详情 + `menu_ids` |
| `PATCH` | `/sys/tenants/{tenant_id}/roles/{role_id}` | 超管 / 租户管理员 | 更新字段与菜单；不含 scope |
| `DELETE` | `/sys/tenants/{tenant_id}/roles/{role_id}` | 超管 / 租户管理员 | 删除角色及 permission 关联 |
| `GET` | `/sys/roles/menu-tree` | 已登录 | 全量 M/C/F 菜单树 |
| `GET` | `/sys/roles/meta/capabilities` | 已登录 | 表单/筛选能力 flags |

### 3.2 配套路由调整

**`GET /sys/tenants/{tenant_id}/workspaces`**：鉴权由 `require_super_admin` 放宽为 `require_tenant_admin(tenant_id)`（超管或该租户管理员），供角色页工作空间下拉与筛选使用。写操作（POST/PATCH/DELETE workspace）仍仅超管。

### 3.3 废弃路由

删除 `backend/app/sys/role/api/router.py` 中 prefix `/workspaces/{workspace_id}/roles` 的全部端点；从 `app/core/api/router.py` 注册保持不变（router 改为租户域路径）。

**保留**：`GET /workspaces/{workspace_id}/users/meta/roles` — 用户表单 assignable roles；内部 repository 按 `workspace_id` 查 `sys_role`，不依赖旧 role router。

### 3.4 Schema 变更

**`SysRoleCreateIn`** 新增：

```python
workspace_id: uuid.UUID  # 必填
```

**`SysRoleListItemOut` / `SysRoleDetailOut`** 新增：

```python
tenant_id: uuid.UUID
tenant_name: str
workspace_name: str
```

（`workspace_id` 保留；列表项始终为非 NULL。）

**`SysRoleCapabilitiesOut`**（新）：

```python
is_super_admin: bool
is_tenant_admin: bool
can_pick_tenant: bool          # 超管 true
can_pick_workspace: bool       # 超管 + 租户管理员 true
fixed_tenant_id: uuid.UUID | None
fixed_tenant_name: str | None
default_filter_tenant_id: uuid.UUID | None   # 超管 null；租户管理员 = 当前租户
default_filter_workspace_id: uuid.UUID | None  # 默认 null（全部工作空间）
```

### 3.5 Service / Repository

**列表查询**：

- `GET /sys/roles`：仅超管；`workspace_id IS NOT NULL`；可选 `tenant_id` / `workspace_id` 过滤；JOIN `sys_tenant` / `sys_workspaces` 取名称。
- `GET /sys/tenants/{tenant_id}/roles`：校验 tenant 存在；`tenant_id` 固定；可选 `workspace_id`；同样排除 `workspace_id IS NULL`（历史数据若存在可保留读取，新建不再产生）。

**创建** `create_role_for_tenant(session, tenant_id, data)`：

1. 校验 `workspace_id` 存在且 `workspace.tenant_id == tenant_id`  
2. 写入 `SysRole(tenant_id=..., workspace_id=..., ...)`  
3. 维护 `sys_role_permission`（与现逻辑一致）

**更新**：不处理 `workspace_id` / `tenant_id` 字段。

**删除**：同现逻辑 — 删 `sys_role_permission` 后删 `sys_role`；若 grant 仍引用该 role，按现有 grant 删除策略（若已有 RESTRICT 语义则 409）。

### 3.6 错误码

| 场景 | code | HTTP |
|------|------|------|
| 非超管访问 `GET /sys/roles` | `auth.forbidden` | 403 |
| 租户管理员访问其他 tenant | `auth.forbidden` | 403 |
| workspace 不属于 tenant | `role.workspace_invalid` | 400 |
| role_key 重复 | `role.conflict` | 409 |
| 角色不存在 | `role.not_found` | 404 |

---

## 4. 前端设计

### 4.1 API 客户端（`frontend/src/api/roles.ts`）

| 函数 | 调用 |
|------|------|
| `getRoleCapabilities()` | `GET /sys/roles/meta/capabilities` |
| `listRolesPlatform(params)` | `GET /sys/roles` |
| `listRolesForTenant(tenantId, params)` | `GET /sys/tenants/{tid}/roles` |
| `listRoleMenuTree()` | `GET /sys/roles/menu-tree` |
| `getRole(tenantId, roleId)` | `GET /sys/tenants/{tid}/roles/{id}` |
| `createRole(tenantId, body)` | `POST /sys/tenants/{tid}/roles` |
| `patchRole(tenantId, roleId, body)` | `PATCH ...` |
| `deleteRole(tenantId, roleId)` | `DELETE ...` |

租户列表：复用 `frontend/src/api/tenants.ts` → `listTenants`（超管）。  
工作空间列表：复用 `listWorkspaces(tenantId)`（鉴权放宽后租户管理员可用）。

### 4.2 RolesPage

**筛选区**（在现有 role_name / status 之前）：

```
[租户 Select]  [工作空间 Select]  [角色名]  [状态]  [搜索] [重置] [新建]
```

- 超管：租户含「全部」；选租户后加载工作空间（含「全部工作空间」）。
- 租户管理员：租户以 Tag 展示；仅工作空间 Select。
- 列表请求：超管且未选租户 → `listRolesPlatform`；否则 → `listRolesForTenant`。
- 表格新增列：`tenant_name`、`workspace_name`。
- 编辑/删除/详情：使用行数据 `tenant_id` + `id`，不依赖 JWT `workspaceId`。

**默认值**（capabilities 加载后）：

| 角色 | 租户 | 工作空间 |
|------|------|----------|
| 超管 | 全部（null） | 全部（null） |
| 租户管理员 | fixed_tenant_id | 全部（null） |

### 4.3 RoleFormDrawer

**Props 扩展**：

```typescript
mode: 'create' | 'edit'
capabilities: SysRoleCapabilities | null
initialScope?: { tenant_id: string; tenant_name: string; workspace_id: string; workspace_name: string }
```

**新建**：

- 超管：`tenant_id` Select → `workspace_id` Select（必选）
- 租户管理员：租户只读 Tag；`workspace_id` Select（必选）
- 提交：`createRole(tenantId, { workspace_id, ...fields })`

**编辑**：

- 顶部只读：`{tenant_name} > {workspace_name}`
- 提交：`patchRole(tenantId, roleId, body)`（无 scope 字段）

**菜单树**：`listRoleMenuTree()`，打开 Drawer 时加载。

### 4.4 i18n 新增键

- `roles.tenant`、`roles.workspace`
- `roles.allTenants`、`roles.allWorkspaces`
- `roles.scopeReadonly`（编辑模式说明）

---

## 5. 迁移与兼容

| 项 | 处理 |
|----|------|
| `sys_role` 表 | 无 DDL 变更 |
| 历史 `workspace_id = NULL` 角色 | 不在新列表默认展示；不阻止只读访问（若存在） |
| `/workspaces/{wid}/roles/*` | 删除 |
| `/workspaces/{wid}/users/meta/roles` | 保留；repository 直查 |

---

## 6. 测试计划

### 6.1 后端

- 超管 `GET /sys/roles` 跨租户分页与 filter 组合
- 非超管 `GET /sys/roles` → 403
- 租户管理员 `GET /sys/tenants/{own_tid}/roles` 成功；`{other_tid}` → 403
- `POST` 创建：`workspace_id` 必填、归属校验、`role_key` 409
- `PATCH` 忽略 scope 字段
- 租户管理员 `GET /sys/tenants/{tid}/workspaces` 可读

### 6.2 前端

- 超管默认全部/全部列表
- 租户管理员租户固定、工作空间筛选
- 新建级联与校验；编辑 scope 只读
- 跨 workspace 行编辑走正确 `tenant_id`

---

## 7. 实现对照（以代码为准，待回填）

| 设计项 | 代码路径 | 状态 |
|--------|----------|------|
| 租户域 role router | `backend/app/sys/role/api/router.py` | 待实现 |
| `require_tenant_role_manager` | `backend/app/sys/role/api/deps.py` | 待实现 |
| workspace 列表鉴权放宽 | `backend/app/sys/tenant/api/router.py` | 待实现 |
| 前端 RolesPage scope | `frontend/src/features/settings/roles/RolesPage.tsx` | 待实现 |
| 前端 RoleFormDrawer scope | `frontend/src/features/settings/roles/RoleFormDrawer.tsx` | 待实现 |
| API 客户端 | `frontend/src/api/roles.ts` | 待实现 |

---

## 8. 决策记录

| 决策 | 选择 | 理由 |
|------|------|------|
| API 方案 | C：租户域 `/sys/tenants/{tid}/roles` | 用户确认；REST 语义与租户管理一致 |
| 角色 scope | 仅具体 workspace | 用户确认；不做租户级通用角色 |
| 编辑 scope | 只读 | 用户确认；避免 grant 与 scope 迁移复杂度 |
| 列表默认 | 超管全部/全部；租户管理员当前租户/全部 workspace | 用户确认 |
| 跨租户列表 | 独立 `GET /sys/roles`（超管） | 纯 tenant 嵌套路由无法表达「全部租户」 |
