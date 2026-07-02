# 用户管理：租户域列表 API 与 scope 联动优化 — 设计说明

**日期**：2026-07-02  
**状态**：已实现（2026-07-02）  
**范围**：超管/租户管理员在用户管理列表与新建/编辑表单中按租户 → 工作空间联动；角色选择与 scope 联动；新增租户级分页列表 API（方案 C）。工作空间管理员保持现网行为。  
**依赖**：
- [2026-06-11-user-management-design.md](./2026-06-11-user-management-design.md)（用户管理基线）
- [2026-06-12-user-form-membership-tenant-design.md](./2026-06-12-user-form-membership-tenant-design.md)（超管新建级联、membership_role 矩阵）
- [2026-07-02-role-management-tenant-scope-design.md](./2026-07-02-role-management-tenant-scope-design.md)（租户域 API、capabilities、UI scope 模式参考）
- [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)（`PermissionGateway`、`tenant:member:manage`）

---

## 1. 目标与成功标准

### 1.1 变更摘要

1. **新增租户级用户列表 API（方案 C）**
   - 超管 / 租户管理员列表走 `GET /sys/tenants/{tenant_id}/workspace-users`。
   - 工作空间管理员继续使用 `GET /workspaces/{workspace_id}/users`。
   - **不修改**现有 `GET /sys/tenants/{tenant_id}/users`（租户管理员选人 picker）。

2. **列表页 scope 筛选**
   - 超管：租户 → 工作空间级联；默认 JWT 当前租户 + 工作空间。
   - 租户管理员：租户固定（Tag 展示）；仅可选当前租户下工作空间；默认同上。
   - 工作空间管理员：无 scope 筛选，列表绑定 JWT workspace（现网）。

3. **新建/编辑表单**
   - **新建**：超管可选租户 → 工作空间；租户管理员租户隐藏、工作空间可选；默认工作空间 = 列表当前筛选。
   - **编辑**：有 scope 权限的操作者（超管 / 租户管理员）见租户 + 工作空间 **只读**（disabled Select）；不可迁移成员关系。
   - **角色联动**：切换工作空间后清空已选 `role_ids`，重载该 workspace 下可分配角色与部门树。

4. **平台级 capabilities**
   - 新增 `GET /sys/users/meta/capabilities`（对齐角色管理 `GET /sys/roles/meta/capabilities`），驱动列表筛选与表单 scope UI。

### 1.2 不在本期

- 编辑用户时变更租户或工作空间成员关系。
- 工作空间管理员的 scope 选择或租户级列表。
- 超管无 `tenant_id` 的全平台用户聚合列表（始终以选定租户为前提）。
- 邀请已有邮箱用户加入 workspace。
- 修改 `email`、`is_super_admin` 等既有禁止项。

### 1.3 成功标准

- 超管/租户管理员切换列表 scope 后，表格展示对应 workspace 成员；新建默认跟随列表 workspace。
- 租户管理员无法访问其他 `tenant_id` 的列表 API（403）。
- 编辑弹窗正确只读展示用户所属 tenant/workspace 名称；PATCH 仍针对用户实际 workspace。
- 切换表单 workspace 后角色选项刷新且已选角色清空。
- 工作空间管理员页面行为与现网一致。
- `GET /sys/tenants/{tenant_id}/users` picker 接口行为不变。

---

## 2. 权限与可见性矩阵

| 操作者 | 列表 API | 列表 scope 筛选 | 新建表单 scope | 编辑表单 scope |
|--------|----------|-----------------|----------------|----------------|
| **平台超管** | 租户级 `workspace-users` | 租户 → 工作空间 | 租户 → 工作空间级联 | 只读 |
| **租户管理员** | 租户级 `workspace-users` | 固定租户 + 工作空间 | 租户 Tag + 工作空间 | 只读 |
| **工作空间管理员** | workspace 级 `/users` | 无 | 无 scope 字段 | 无 scope 字段 |
| **普通 member** | 只读列表（若有菜单权限） | 同工作空间管理员 | 无新建 | — |

**列表读权限**（`GET .../workspace-users`）：

1. 超管 → 任意 `tenant_id`
2. `is_tenant_admin(actor, tenant_id)` → 仅本租户
3. 否则 → 403

**写操作**（创建/更新/删除）：沿用现有 workspace 级 deps（`require_workspace_manager_or_super_admin`、`require_create_workspace_scope` 等）；目标 `workspace_id` 须在操作者有权限的范围内。

---

## 3. 后端设计

### 3.1 新增路由

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| `GET` | `/sys/tenants/{tenant_id}/workspace-users` | 超管 / 租户管理员 | 租户内 workspace 成员分页列表 |
| `GET` | `/sys/users/meta/capabilities` | 已登录 | 列表/表单 scope 能力 flags |

### 3.2 `GET /sys/tenants/{tenant_id}/workspace-users`

**Query 参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `workspace_id` | UUID | **UI 始终传入**；筛选指定 workspace 成员 |
| `email` / `nickname` / `phone` | string | 同现网 workspace 列表 |
| `status` | bool | 同现网 |
| `membership_role` | string | `admin` / `member` |
| `role_id` | UUID | 按该 workspace 内 role grant 过滤 |
| `page` / `page_size` | int | 分页 |

**`workspace_id` 未传时（仅 API 层支持，UI 不使用）**：返回租户下所有 workspace 成员；同一用户属于多个 workspace 时出现多行（每行对应一条 `sys_workspace_user` 记录）。

**响应**：复用 `SysUserListPageOut`；`SysUserListItemOut` 扩展：

```python
tenant_id: uuid.UUID
tenant_name: str
workspace_id: uuid.UUID
workspace_name: str
```

其余字段（`role_ids`、`role_names`、`membership_role`、`can_hard_delete` 等）与现网 workspace 列表项一致，按**该行对应的 `workspace_id`** 计算。

**Repository 查询**：

```text
sys_user
  JOIN sys_workspace_user ON user_id
  JOIN sys_workspaces ON workspace_id
WHERE sys_workspaces.tenant_id = :tenant_id
  [AND sys_workspace_user.workspace_id = :workspace_id]
```

`role_id` 筛选 join `sys_user_grant`（`scope_type=workspace`, `scope_id=workspace_id`）。

复用 `user_service._build_list_row` / `_row_to_response_dict` 逻辑，传入每行的 `workspace_id` 与解析出的 `tenant_id`。

### 3.3 `GET /sys/users/meta/capabilities`

从 JWT 解析 `tid` / `wid`（与角色 capabilities 同模式），返回：

```python
is_super_admin: bool
is_tenant_admin: bool
can_pick_tenant: bool              # 超管 true
can_pick_workspace: bool             # 超管 + 租户管理员 true
fixed_tenant_id: uuid.UUID | None
fixed_tenant_name: str | None
default_filter_tenant_id: uuid.UUID | None   # JWT tid（超管与租户管理员均默认当前 JWT 租户）
default_filter_workspace_id: uuid.UUID | None  # JWT wid
# membership_role 表单字段（保留现网语义）
actor_workspace_role: str | None
can_edit_membership_role: bool
assignable_membership_roles: list[str]
```

**废弃/替代**：`can_pick_tenant_workspace` 由 `can_pick_tenant` 替代；`GET /workspaces/{id}/users/meta/capabilities` 可保留供 workspace 管理员表单使用，或内部调用同一 `build_user_capabilities` service。

### 3.4 保留不变的 workspace 级路由

| 路由 | 用途 |
|------|------|
| `GET/POST/PATCH/DELETE /workspaces/{wid}/users/...` | 工作空间管理员列表与 CRUD |
| `GET /workspaces/{wid}/users/meta/roles` | 按目标 workspace 加载可分配角色 |
| `GET /workspaces/{wid}/users/meta/departments` | 部门树 |
| `GET /workspaces/{wid}/users/meta/tenants` | 超管表单租户选项（可逐步改用 `/sys/tenants`） |
| `GET /sys/tenants/{tid}/users` | 租户成员 picker（**禁止破坏**） |
| `GET /sys/tenants/{tid}/workspaces` | 工作空间列表（租户管理员可读，角色页已用） |

### 3.5 用户详情 enrich

`GET /workspaces/{wid}/users/{user_id}` 响应补充 `tenant_name`、`workspace_name`，供编辑弹窗只读展示（列表行亦可携带，减少额外请求）。

---

## 4. 前端设计

### 4.1 `UsersPage`

**capabilities 加载**：`GET /sys/users/meta/capabilities` → 初始化 `filterTenantId`、`filterWorkspaceId`（默认 JWT 租户 + 工作空间）。

**列表请求分支**：

```typescript
if (capabilities.can_pick_workspace) {
  listTenantWorkspaceUsers(effectiveTenantId, {
    workspace_id: effectiveWorkspaceId,
    ...filters,
    page,
    page_size,
  })
} else {
  listUsers(jwtWorkspaceId, { ...filters, page, page_size })
}
```

**筛选区 UI**（参照 `RolesPage.tsx`）：

- 超管：`Select` 租户 → `Select` 工作空间（级联）
- 租户管理员：`Tag` 固定租户 + `Select` 工作空间
- 工作空间管理员：无 scope 控件

租户切换 → 重载工作空间列表 → 若当前 workspace 不在新租户下则选中列表首项或 JWT workspace（若存在）。

**新建**：`openCreate` 默认 `workspace_id = effectiveWorkspaceId`（列表当前筛选）。

**编辑**：从列表行读取 `tenant_id`、`tenant_name`、`workspace_id`、`workspace_name` 构造 `initialScope`；`patchUser` / grant API 使用行的 `workspace_id`。

### 4.2 `UserFormDrawer`

对齐 `RoleFormDrawer.tsx` 三种 UI 态：

| 模式 | 超管 | 租户管理员 | 工作空间管理员 |
|------|------|-----------|---------------|
| 新建 | 租户 Select → 工作空间 Select | 租户 Tag + 工作空间 Select | 无 scope |
| 编辑 | 租户/工作空间 disabled Select | 同上 | 无 scope |

**联动**（新建 + 有 scope 时）：

1. `tenant_id` onChange → 清空 `workspace_id`、`role_ids` → 加载 workspaces
2. `workspace_id` onChange → **清空 `role_ids`** → `listUserAssignableRoles(wsId)` + `listUserDepartmentTree(wsId)`

**capabilities**：列表页传入或 drawer 内读取 `GET /sys/users/meta/capabilities`。

**租户/工作空间选项来源**：

- 超管：`listTenants()` + `listWorkspaces(tenantId)`（`frontend/src/api/tenants.ts`）
- 租户管理员：`listWorkspaces(fixed_tenant_id)`

### 4.3 API 客户端（`frontend/src/api/users.ts`）

新增：

```typescript
getUserListCapabilities(): Promise<SysUserListCapabilities>
listTenantWorkspaceUsers(tenantId: string, params: SysUserListParams & { workspace_id?: string })
```

扩展 `SysUserListItem`：`tenant_name`、`workspace_name`。

---

## 5. 数据流

```text
进入 UsersPage
  → GET /sys/users/meta/capabilities
  → 初始化 filterTenantId / filterWorkspaceId（JWT 默认）
  → can_pick_workspace?
       Yes → GET /sys/tenants/{tid}/workspace-users?workspace_id={wid}
       No  → GET /workspaces/{jwt_wid}/users

新建
  → 表单 workspace 默认 = 列表 effectiveWorkspaceId
  → 切换 workspace → 清空 role_ids → 重载 roles/departments
  → POST /workspaces/{target_wid}/users

编辑
  → 只读展示 initialScope（来自列表行）
  → PATCH /workspaces/{row.workspace_id}/users/{id}
  → replaceWorkspaceRoleGrants(tenantId, row.workspace_id, userId, roleIds)
```

---

## 6. 错误处理与边界

| 场景 | 处理 |
|------|------|
| 跨 workspace 新建成功 | 保留 `users.createSuccessOtherWorkspace` 提示 |
| 租户管理员访问其他 tenant 列表 | 403 + `Result` 无权限 |
| 筛选 workspace 无成员 | 空表格，非错误 |
| `role_id` 筛选 | 必须结合 `workspace_id`（同行 workspace 的 grant） |
| picker `GET /sys/tenants/{tid}/users` | 行为与响应结构不变 |

---

## 7. 测试要点

### 后端

- `workspace-users`：超管跨租户、租户管理员本租户、越权 403
- `workspace_id` 筛选结果与现网 `GET /workspaces/{wid}/users` 一致
- `role_id` 筛选限定在指定 workspace grant
- `capabilities` 各角色 flags 正确；`default_filter_*` 来自 JWT
- picker 接口回归

### 前端

- 超管：scope 切换 → 列表变化；新建默认 workspace；编辑只读 scope
- 租户管理员：仅本租户 workspaces；新建/编辑正确
- 工作空间管理员：无 scope UI，旧 API 不变
- 切换 workspace 清空角色并重载选项
- 跨 workspace 创建成功提示

---

## 8. 实现顺序建议

1. 后端：`build_user_capabilities` + `GET /sys/users/meta/capabilities`
2. 后端：`list_tenant_workspace_users_page` repository + `GET .../workspace-users`
3. 后端：列表项/详情补充 `tenant_name`、`workspace_name`
4. 前端：API 类型与客户端函数
5. 前端：`UsersPage` scope 筛选 + 双轨列表
6. 前端：`UserFormDrawer` scope UI + 角色联动
7. 联调与回归（含 workspace 管理员、picker）

---

## 9. 方案选型记录

| 方案 | 说明 | 结论 |
|------|------|------|
| A | 扩展现有 capabilities，列表切换 `effectiveWorkspaceId` path | 改动小，未选用 |
| B | 前端混用角色 capabilities | 域耦合，未选用 |
| **C** | **新增租户级分页列表 API + 平台 capabilities** | **已确认** |

选用理由：API 语义贴合租户管理视角；列表项天然携带 scope 名称；与角色管理租户域迁移方向一致。需注意与现有 `/sys/tenants/{tid}/users` picker 路径区分，新端点使用 `workspace-users`。
