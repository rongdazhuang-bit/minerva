# 用户表单：空间角色权限与超管租户/空间选择 — 设计说明

**日期**：2026-06-12  
**状态**：已实现（2026-06-12）  
**范围**：用户管理新建/编辑表单中「空间角色」按操作者权限显隐与可分配值约束；平台超管新建用户时可级联选择租户与工作空间。  
**依赖**：
- [2026-06-11-user-management-design.md](./2026-06-11-user-management-design.md)（已实现的用户管理基线）
- 租户/工作空间 API：`/sys/tenants`、`/sys/tenants/{tenant_id}/workspaces`
- 身份域 `MembershipRole`、`User.is_super_admin`（见 [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)）

**权限网关（Supersede 部分）**：本 spec 中 `owner` 成员角色、`is_super_admin_user` 旁路与 capabilities 分散判定，已由 [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md) 收敛至 `PermissionGateway` 与 `/auth/me/authorization`。

---

## 1. 目标与成功标准

### 1.1 变更摘要

1. **空间角色（`membership_role`）**
   - 仅 workspace **`owner` / `admin`** 操作者可见并可编辑。
   - workspace **`member`** 操作者：表单不展示该字段；新建用户固定为 `member`。
   - 可分配值按操作者角色区分（见 §2.2）。
   - 后端对创建/更新做权威校验，防止 API 绕过。

2. **超管指定租户与工作空间（仅新建）**
   - 平台超管（`sys_user.is_super_admin`）**新建**用户时可见「租户 → 工作空间」级联选择。
   - 默认预选：当前 JWT 上下文下的租户与工作空间。
   - 用户写入**所选工作空间**；`sys_tenant_user` 的 `tenant_id` 取自该 workspace 所属租户（与 workspace 一致）。
   - 非超管：不展示租户/空间字段，行为与现网一致（仅当前页 workspace）。

3. **编辑模式**
   - 不展示租户/工作空间选择，不可迁移成员关系。
   - 空间角色规则仍按 §2.2 生效；特殊只读场景见 §2.3。

### 1.2 不在本期

- 编辑用户时变更租户或工作空间成员关系。
- 邀请已有邮箱用户加入 workspace。
- 修改 `email`、`is_super_admin` 等既有禁止项。

### 1.3 成功标准

- 各角色操作者看到的表单字段与可分配空间角色符合矩阵；非法 `membership_role` 返回 400。
- 超管可跨 workspace 创建用户且租户成员关系正确；非超管无法向其他 workspace 创建。
- 跨 workspace 创建后前端有明确成功提示；当前列表不出现新用户属预期。

---

## 2. 空间角色权限矩阵

### 2.1 操作者与 UI

| 操作者 workspace 角色 | 表单展示「空间角色」 | 新建默认值 | 可分配 `membership_role` |
|----------------------|---------------------|------------|--------------------------|
| `member` | 否 | `member`（不传或由后端默认） | — |
| `admin` | 是 | `member` | `admin`, `member` |
| `owner` | 是 | `member` | `owner`, `member` |
| **平台超管** | 是 | `member` | **`owner`, `admin`, `member`（始终三档，与是否在目标 workspace 有成员身份无关）** |

说明：

- **非超管**：`owner` 不可分配 `admin`；`admin` 不可分配 `owner`。
- **超管**：不受上述限制，可分配并修改任意空间角色。
- 列表/筛选区成员资格筛选项不变（仍可按 owner/admin/member 筛选）。

### 2.2 编辑特殊场景

| 目标用户当前角色 | 操作者 | 行为 |
|------------------|--------|------|
| `admin` | `owner`（非超管） | 空间角色字段**只读**展示当前值 `admin`；PATCH **不传** `membership_role`；附说明文案 |
| `owner` | `admin`（非超管） | 不允许 PATCH `membership_role` → **403** `user.membership_role_forbidden` |
| 任意 | **平台超管** | 可编辑三档空间角色（含将 `admin`/`owner` 互调） |
| 其他 | 符合 §2.1 矩阵 | 正常可编辑 |

---

## 3. 后端设计

### 3.1 新增 `GET /workspaces/{workspace_id}/users/meta/capabilities`

**鉴权**：`require_workspace_member`（与 `meta/departments`、`meta/roles` 一致）。

**说明**：`workspace_id` 为**有效目标 workspace**（超管新建时可为所选空间，非当前 JWT workspace）。

**响应**：

```json
{
  "is_super_admin": false,
  "actor_workspace_role": "admin",
  "can_edit_membership_role": true,
  "assignable_membership_roles": ["admin", "member"],
  "can_pick_tenant_workspace": false
}
```

| 字段 | 规则 |
|------|------|
| `is_super_admin` | `is_super_admin_user(actor)` |
| `actor_workspace_role` | 操作者在**该** `workspace_id` 的 `MembershipRole`；非成员为 `null` |
| `can_edit_membership_role` | `owner` 或 `admin` 或（超管且无成员身份时的代管）为 `true`；纯 `member` 为 `false` |
| `assignable_membership_roles` | §2.1 矩阵；`can_edit_membership_role=false` 时为 `[]` |
| `can_pick_tenant_workspace` | 仅 `is_super_admin=true`（前端仅用于**新建**显隐） |

**实现**：`user_service.get_actor_capabilities(session, workspace_id, actor_user_id)`。

### 3.2 写权限：超管旁路

现有 `POST`/`PATCH` 使用 `require_workspace_owner_or_admin`，无法向操作者非 admin 的 workspace 写。

**调整**：新增依赖 `require_workspace_manager_or_super_admin`：

- 若 `is_super_admin_user` → 允许（仍校验 workspace 存在）。
- 否则沿用 `require_workspace_owner_or_admin`。

仅用于用户管理写路由（`POST`、`PATCH`、`DELETE` 系列），不全局修改 `require_workspace_owner_or_admin`。

### 3.3 创建 `POST /workspaces/{workspace_id}/users`

- **路径 `workspace_id`**：目标 workspace（用户将被加入的空间）。
- **非超管**：`workspace_id` 必须与 JWT `wid` 一致，否则 **403** `auth.forbidden`。
- **超管**：允许任意有效 `workspace_id`。
- **请求体**：不变（不增加 `tenant_id`）；租户由目标 workspace 推导。
- **`membership_role` 校验**：
  1. 须在 `assignable_membership_roles` 内，否则 **400** `user.membership_role_forbidden`。
  2. `can_edit_membership_role=false` 时若 body 含非 `member` 的 `membership_role` → **400**。
- **事务**：与现网一致 — `sys_user` → `sys_workspace_user` → `sys_tenant_user`（`tenant_id` = workspace.tenant_id）→ `sys_user_role`。
- **部门 / `role_ids`**：校验针对路径 `workspace_id`。

### 3.4 更新 `PATCH /workspaces/{workspace_id}/users/{user_id}`

- 不接收 `tenant_id` / `workspace_id` / 成员迁移字段。
- `membership_role` 在 body 中出现时：
  - 操作者 `can_edit_membership_role=false` → **403**。
  - 不在 `assignable_membership_roles` → **400** `user.membership_role_forbidden`。
  - 目标为 `owner` 且操作者为 `admin` → **403** `user.membership_role_forbidden`。
  - 目标为 `admin` 且操作者为 `owner`（当前值不在 owner 可分配列表）→ 前端不传；若 API 仍收到变更请求 → **400**。

### 3.5 租户 / 工作空间 meta（超管新建）

复用 `app/sys/tenant/infrastructure/repository.py` 查询 **`sys_tenant`**、**`sys_workspaces`**（仅 `status=true`），挂载在用户管理 meta 下：

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workspaces/{workspace_id}/users/meta/tenants` | `sys_tenant` 下拉选项 |
| GET | `/workspaces/{workspace_id}/users/meta/tenants/{tenant_id}/workspaces` | 该租户下 `sys_workspaces` 下拉选项 |

鉴权：`require_workspace_member` + service 层 `is_super_admin_user`（非超管 **403**）。

`capabilities.default_tenant_id`：当前 workspace 所属租户（来自 `sys_workspaces.tenant_id`），用于表单默认预选。

### 3.6 错误码补充

| 场景 | HTTP | code |
|------|------|------|
| `membership_role` 不在可分配范围 | 400 | `user.membership_role_forbidden` |
| 非超管向非当前 workspace 创建 | 403 | `auth.forbidden` |
| admin 修改 owner 的 `membership_role` | 403 | `user.membership_role_forbidden` |
| 无空间角色编辑权却 PATCH `membership_role` | 403 | `user.membership_role_forbidden` |

### 3.7 代码落点

| 项 | 位置 |
|----|------|
| capabilities schema | `backend/app/sys/user/api/schemas.py` |
| capabilities 路由 | `backend/app/sys/user/api/router.py` |
| 角色校验 / capabilities | `backend/app/sys/user/service/user_service.py` |
| 超管写旁路 | `backend/app/core/api/deps.py` 或 `backend/app/sys/user/api/deps.py` |
| 测试 | `backend/tests/test_user_api.py`、`test_user_service.py` |

---

## 4. 前端设计

### 4.1 有效 workspace

**`effectiveWorkspaceId`**：

| 模式 | 普通用户 | 超管 |
|------|----------|------|
| 新建 | 当前页 `workspaceId` | 级联所选 workspace；默认当前 JWT workspace |
| 编辑 | 当前页 `workspaceId` | 同左 |

打开 Drawer 及切换所选 workspace 时，基于 `effectiveWorkspaceId` 请求：

- `meta/capabilities`
- `meta/departments`
- `meta/roles`

### 4.2 `UserFormDrawer` 字段

**超管新建 · 租户 / 工作空间**（`can_pick_tenant_workspace`，仅 `mode === 'create'`）：

1. 租户 `Select` — `listTenants`（建议 `status=true`）
2. 工作空间 `Select` — `listWorkspaces(tenantId)`，依赖租户
3. 默认：当前 `workspaceId` 所属租户 + 当前 workspace 预选
4. 切换租户：清空 workspace，重载空间列表；切换 workspace：重载 meta 三接口

**空间角色**：

- `can_edit_membership_role=false`：不渲染；提交 `membership_role: 'member'` 或不传（与后端约定一致）。
- `can_edit_membership_role=true`：`Select`，options = `assignable_membership_roles`。
- 编辑且当前 `membership_role` 不在 `assignable_membership_roles`：只读展示 + `Alert`；PATCH 不含 `membership_role`。

**表单字段顺序（超管新建）**：租户 → 工作空间 → 邮箱 → 密码 → 昵称 → 手机 → 状态 → 空间角色（若有）→ 部门 → 角色 → 备注。

### 4.3 `UsersPage`

- `createUser(targetWorkspaceId, body)` — `targetWorkspaceId` 来自 Drawer（超管所选或默认）。
- 创建成功且 `targetWorkspaceId !== pageWorkspaceId`：使用 `users.createSuccessOtherWorkspace` 提示。
- 其余列表/权限逻辑不变（`isWorkspaceManager` 控制写操作入口）。

### 4.4 API 客户端

`frontend/src/api/users.ts`：

```ts
export type SysUserCapabilities = {
  is_super_admin: boolean
  actor_workspace_role: string | null
  can_edit_membership_role: boolean
  assignable_membership_roles: string[]
  can_pick_tenant_workspace: boolean
}

export function getUserCapabilities(workspaceId: string): Promise<SysUserCapabilities>
```

### 4.5 i18n（`zh-CN.json` / `en.json`）

| Key | 说明 |
|-----|------|
| `users.tenant` | 租户 |
| `users.workspace` | 工作空间 |
| `users.tenantPlaceholder` | 请选择租户 |
| `users.workspacePlaceholder` | 请选择工作空间 |
| `users.createSuccessOtherWorkspace` | 用户已添加到所选工作空间，当前列表不会显示该用户 |
| `users.membershipRoleReadonlyAdmin` | 该用户为空间管理员，仅空间管理员可调整此角色 |

错误码 `user.membership_role_forbidden` 接入现有 `errors.*` 映射（若已有模式）。

### 4.6 UI 规范

遵守 [2026-06-11-user-management-design.md](./2026-06-11-user-management-design.md) §4.4：Drawer 520px、`allowClear`、`minerva-scrollbar-styled`、Popconfirm 不变。

---

## 5. 测试与验收

### 5.1 后端自动化

- capabilities 各角色返回值正确（含超管无成员身份代管）。
- 创建：`admin`→`owner` **400**；`owner`→`admin` **400**；合法组合 **201**。
- 超管跨 workspace 创建；`sys_tenant_user.tenant_id` 与 workspace 一致。
- 非超管 `workspace_id ≠ jwt.wid` 创建 **403**。
- PATCH：admin 改 owner 的 `membership_role` **403**。

### 5.2 前端手动

1. workspace `admin`：空间角色仅 admin/member，默认 member。
2. workspace `owner`：仅 owner/member；编辑 admin 用户时空间角色只读。
3. workspace `member`：无写入口（与现网一致）。
4. 超管：租户→空间级联；默认当前上下文；切换空间后部门/角色刷新。
5. 超管跨空间创建：专用成功提示；当前列表无新行。

---

## 6. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-12 | 初稿：空间角色按操作者权限矩阵；超管新建租户/空间级联；capabilities meta；超管写旁路 |
| 2026-06-12 | 实现完成 |

---

## 10. 实现对照（以代码为准，2026-06-12）

| spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| membership 矩阵纯函数 | `backend/app/sys/user/service/user_service.py` | `resolve_assignable_membership_roles` 等 |
| `get_actor_capabilities` | 同上 | |
| create/update 校验 | 同上 `create_user` / `update_user` | |
| `meta/capabilities` | `backend/app/sys/user/api/router.py` | |
| 超管写旁路 / create scope | `backend/app/sys/user/api/deps.py` | |
| 前端 capabilities API | `frontend/src/api/users.ts` | `getUserCapabilities` |
| 表单 Drawer | `frontend/src/features/settings/users/UserFormDrawer.tsx` | 租户级联、空间角色条件渲染 |
| 列表页提交 | `frontend/src/features/settings/users/UsersPage.tsx` | `targetWorkspaceId` |
| i18n | `frontend/src/i18n/locales/zh-CN.json`、`en.json` | |
| 测试 | `backend/tests/test_user_service.py`、`test_user_api.py` | 21 passed |
