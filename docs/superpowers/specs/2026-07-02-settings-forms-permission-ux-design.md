# 设置页表单权限 UX 优化 — 设计说明

**日期**：2026-07-02  
**状态**：已实现（2026-07-02，含 P0–P3 审查修复）  
**范围**：租户管理、角色管理、用户管理三个模块的新增/编辑弹窗权限数据联动与管理员配置项优化。  
**依赖**：
- [2026-07-01-tenant-page-ux-design.md](./2026-07-01-tenant-page-ux-design.md)（租户菜单权限与管理员多选）
- [2026-07-02-role-management-tenant-scope-design.md](./2026-07-02-role-management-tenant-scope-design.md)（角色租户 scope、菜单树基线）
- [2026-06-12-user-form-membership-tenant-design.md](./2026-06-12-user-form-membership-tenant-design.md)（`membership_role` 矩阵）
- [2026-07-02-user-management-scope-design.md](./2026-07-02-user-management-scope-design.md)（用户 scope 联动、角色按 workspace 加载）
- [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)（`tenant_admin` grant）

---

## 1. 目标与成功标准

### 1.1 变更摘要

1. **租户管理**：新建租户弹窗完全隐藏「租户管理员」字段；仅在编辑模式展示并可配置。
2. **角色管理**：新增/编辑角色弹窗中「菜单权限」树按弹窗内已选租户已授权菜单展示（补全祖先节点）；保存时仅持久化租户授权范围内的 `menu_id`。
3. **用户管理**：
   - 「角色」多选按已选租户 → 工作空间加载（未选工作空间时禁用）。
   - 新增「租户管理员」下拉（管理员 / 成员），仅超管可见可编辑，与弹窗内已选租户绑定。
   - 「空间管理员」复用 `membership_role`，调整标签与可见性：超管/租户管理员可编辑；工作空间管理员及其他只读；默认成员。

### 1.2 不在本期

- 编辑用户时迁移租户或工作空间成员关系。
- 非超管在用户表单中配置租户管理员（仍走租户管理页 `PUT .../admins`）。
- 修改 `GET /sys/roles/menu-tree` 全局端点语义（保留兼容，角色表单改走租户域新端点）。
- 角色/用户列表页筛选逻辑变更。

### 1.3 成功标准

- 新建租户表单不出现「租户管理员」字段；保存时不调用 `putTenantAdmins`。
- 超管在角色新建时切换租户，菜单树随之变化；提交超出该租户授权范围的 `menu_id` 返回 400。
- 超管在用户表单为某租户用户设置「租户管理员 = 管理员」后，`sys_user_grant(tenant_admin)` 正确写入。
- 工作空间管理员在用户表单中可见「空间管理员」当前值但不可修改；不可见「租户管理员」字段。
- 用户表单未选工作空间时，「角色」选择框禁用且不发起 roles 请求。

---

## 2. 已确认产品决策

| 议题 | 决策 |
|------|------|
| 用户表单「租户管理员」scope | 以弹窗内已选租户为准 |
| 用户表单「租户管理员」控件 | Select 单选：管理员 / 成员（默认成员） |
| 用户表单「空间管理员」 | 复用 `membership_role`，改标签与可见性规则 |
| 租户新建「租户管理员」 | 新建模式完全隐藏，仅编辑模式显示 |
| 角色菜单树过滤 | 补全祖先节点且可勾选；保存时 `menu_ids ⊆ 租户授权菜单` |

---

## 3. 租户管理

### 3.1 前端

**`TenantPermissionFields`**

- 新增 prop `showAdmins?: boolean`，默认 `true`。
- `showAdmins === false` 时不渲染 `admin_user_ids` Form.Item。

**`TenantFormDrawer`**

- `mode === 'create'`：`showAdmins={false}`。
- 新建时不再调用 `listPlatformUserOptions()`。
- 提交 permissions 时 `admin_user_ids` 固定为 `[]`（或由 `TenantsPage` 跳过 `putTenantAdmins`）。

**`TenantsPage.handleSubmit`**

- 创建成功后：仅 `putTenantPermissions`；**不**调用 `putTenantAdmins`。
- 编辑成功后：保持现网 `putTenantPermissions` + `putTenantAdmins`。

**`TenantPermissionDrawer`**

- 无变更（仅编辑场景，继续展示管理员多选）。

### 3.2 后端

无 API 变更。

---

## 4. 角色管理 — 菜单权限按租户过滤

### 4.1 后端

**新增服务** `list_menu_tree_for_tenant_role_assignment(session, tenant_id)`：

1. 从 `sys_tenant_permission` 读取 `authorized_ids`。
2. 调用 `menu_service.list_menu_tree` 得全量树。
3. 计算 `display_ids = authorized_ids ∪ ancestors(authorized_ids)`（沿 `parent_id` 向上补全）。
4. 裁剪树，仅保留 `display_ids` 内节点，保持层级结构。

**新增 API**

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| `GET` | `/sys/tenants/{tenant_id}/roles/menu-tree` | `require_tenant_role_viewer` | 租户域角色菜单树 |

**角色 create/patch 校验**（租户域路由内，解析 `tenant_id` 后）：

```python
submitted_menu_ids ⊆ tenant_authorized_menu_ids
```

- 违反时：`400`，code 建议 `role.menu_not_in_tenant`（仅当 menu_id **不在租户展示树**内，即非授权且非其祖先）。
- 持久化值为校验后的集合：展示树内的祖先节点若被勾选但未在 `authorized_ids` 中，**静默过滤**，不写入 `sys_role_permission`。

**保留** `GET /sys/roles/menu-tree`：不删除；角色管理 UI 改调租户域端点。

### 4.2 前端

**`RolesPage`**

- 移除页面初始化时一次性 `loadMenuTree()`（全局树）。
- 打开 Drawer 时按租户加载：
  - **新建**：监听表单 `tenant_id`；有值则 `GET /sys/tenants/{tid}/roles/menu-tree`；无值则 `menuTree = []` 并展示提示。
  - **编辑**：用角色所属 `tenant_id` 加载。
- 切换租户（新建）：重载树；`checkedKeys = checkedKeys.filter(id => validInNewTree)`。

**`RoleFormDrawer`**

- 无结构变更；继续接收 `menuTree` prop。
- 可选：租户未选时在菜单权限区展示 `roles.selectTenantForMenus` 类提示文案。

**树交互**

- 展示节点含祖先；M/C/F 类型与现网一致。
- 父子联动、全选等行为不变。
- 编辑回显：角色已有但租户已收回授权的 menu_id 不在树中展示，保存后自然剔除。

---

## 5. 用户管理

### 5.1 角色选择框

**行为**（强化现网 scope 联动）：

- 仅当 `effectiveWorkspaceId` 有值时调用 `GET /workspaces/{wid}/users/meta/roles`。
- 未选工作空间：`role_ids` Select `disabled`，placeholder 提示先选工作空间。
- 切换租户或工作空间：清空 `role_ids` 并重载（保持现网逻辑）。

无需新增 roles API；repository 已按 `workspace_id` 查 `sys_role`。

### 5.2 「租户管理员」Select

| 属性 | 规则 |
|------|------|
| 字段名（表单） | `tenant_admin_role`：`admin` \| `member`（仅前端；映射 grant） |
| 可见 | `listCapabilities.is_super_admin && effectiveTenantId != null` |
| 可编辑 | 同可见 |
| 默认 | `member` |
| 数据 scope | 弹窗内 `effectiveTenantId` 对应租户的 `tenant_admin` grant |

**后端新增 API**（仅超管）

| 方法 | 路径 | Body | 响应 |
|------|------|------|------|
| `GET` | `/sys/tenants/{tenant_id}/users/{user_id}/tenant-admin` | — | `{ is_tenant_admin: bool }` |
| `PUT` | `/sys/tenants/{tenant_id}/users/{user_id}/tenant-admin` | `{ enabled: bool }` | `{ is_tenant_admin: bool }` |

**服务** `set_user_tenant_admin(session, *, tenant_id, user_id, enabled, granted_by_user_id)`：

- `enabled=true`：若不存在则插入 `sys_user_grant(grant_type=tenant_admin, scope_type=tenant, scope_id=tenant_id)`。
- `enabled=false`：软删或移除对应 grant（与 `replace_tenant_admins` 一致策略）。
- 校验 `User` 存在；不要求用户已是 `sys_tenant_user` 成员（与现网 `replace_tenant_admins` 一致）。

**编辑加载**：打开编辑 Drawer 且为超管时，并行请求 `GET .../tenant-admin` 填充 Select。

**保存顺序**（`UsersPage`）：

1. `createUser` / `patchUser`
2. 若超管且 `tenant_admin_role` 相对初始值有变 → `PUT .../tenant-admin`
3. 角色 Grant（现网 `replaceWorkspaceRoleGrants` 或 body `role_ids` 路径）

### 5.3 「空间管理员」（`membership_role`）

| 操作者 | 可见 | 可编辑 | UI |
|--------|------|--------|-----|
| 超管 | ✓ | ✓ | Select：管理员 / 成员 |
| 租户管理员 | ✓ | ✓ | Select |
| 工作空间管理员 | ✓ | ✗ | disabled Select 展示当前值 |
| 普通成员 | — | — | 无管理入口 |

**后端调整** `can_edit_membership_role`：

- **现网**：超管 / 租户管理员 / 工作空间管理员可编辑。
- **本需求**：仅 `is_super_admin || is_tenant_admin` 可编辑。

**新增** `can_view_membership_role`：

- 有用户管理写权限且打开表单时为 `true`（含工作空间管理员只读场景）。

**默认**：新建 `membership_role = member`。

**前端**：

- i18n：`users.membershipRole` 文案改为「空间管理员」（或新增 `users.workspaceAdminRole` 后替换引用）。
- 移除工作空间管理员「仅空间管理员可调整此角色」的 info Alert（改为只读 Select，不再暗示可编辑）。
- `can_view_membership_role === true && !can_edit_membership_role` 时渲染 disabled Select。

### 5.4 Capabilities 扩展

**`SysUserCapabilities`**（workspace 级 meta）与 **`SysUserListCapabilities`** 按需扩展：

```typescript
can_edit_tenant_admin: boolean      // is_super_admin
can_view_membership_role: boolean    // 有表单访问权限时为 true
can_edit_membership_role: boolean    // is_super_admin || is_tenant_admin（收窄）
```

list capabilities 至少提供 `can_edit_tenant_admin`（驱动租户管理员字段显隐）；表单 capabilities 提供 membership 三项。

---

## 6. 权限与可见性矩阵（用户表单）

| 字段 | 超管 | 租户管理员 | 工作空间管理员 |
|------|------|------------|----------------|
| 租户 scope（新建） | 可选 | Tag 固定 | 无 |
| 工作空间 scope（新建） | 可选 | 可选 | 无 |
| 租户管理员 Select | 可见可编辑 | 隐藏 | 隐藏 |
| 空间管理员 Select | 可见可编辑 | 可见可编辑 | 可见只读 |
| 角色多选 | 需先选 workspace | 同左 | 需 workspace（JWT） |

---

## 7. 错误处理

| 场景 | 处理 |
|------|------|
| 新建租户 | 不调用 `putTenantAdmins` |
| 角色 menu_id 不在租户展示树内 | `400 role.menu_not_in_tenant` |
| 角色 menu_id 为展示树内祖先（非授权） | 静默过滤，仅持久化授权 id |
| 非超管调用 tenant-admin API | `403 auth.forbidden` |
| 未选工作空间 | 前端禁用角色 Select，不请求 meta/roles |
| tenant-admin 目标用户不存在 | `404 user.not_found` |
| 编辑时 tenant 已收回某 menu | 树不展示；保存后 role permission 不含该 id |

---

## 8. 前端文件清单

| 文件 | 变更 |
|------|------|
| `frontend/src/features/settings/tenants/TenantPermissionFields.tsx` | `showAdmins` prop |
| `frontend/src/features/settings/tenants/TenantFormDrawer.tsx` | 新建隐藏管理员、跳过 platform users 加载 |
| `frontend/src/features/settings/tenants/TenantsPage.tsx` | 创建时跳过 putTenantAdmins |
| `frontend/src/features/settings/roles/RolesPage.tsx` | 按租户加载 menu-tree |
| `frontend/src/features/settings/roles/RoleFormDrawer.tsx` | 可选空态提示 |
| `frontend/src/api/roles.ts` | `listRoleMenuTreeForTenant(tenantId)` |
| `frontend/src/features/settings/users/UserFormDrawer.tsx` | 租户管理员 Select、空间管理员可见性、角色禁用态 |
| `frontend/src/features/settings/users/UsersPage.tsx` | 保存 tenant-admin、编辑加载 |
| `frontend/src/api/users.ts` | tenant-admin API 客户端 |
| `frontend/src/api/tenantPermissions.ts` | 可选：tenant-admin 客户端放此或 users.ts |
| `frontend/src/i18n/locales/zh-CN.json` | 新文案 |

---

## 9. 后端文件清单

| 文件 | 变更 |
|------|------|
| `backend/app/sys/role/service/role_service.py` | 租户菜单树、create/patch 校验 |
| `backend/app/sys/role/api/router.py` | `GET .../roles/menu-tree` 租户域 |
| `backend/app/sys/user/service/user_service.py` | `can_edit_membership_role` 收窄、`can_view_membership_role` |
| `backend/app/sys/user/api/schemas.py` | capabilities 字段 |
| `backend/app/sys/tenant/service/tenant_permission_service.py` | `set_user_tenant_admin` |
| `backend/app/sys/tenant/api/router.py` | tenant-admin GET/PUT |
| `backend/app/sys/tenant/api/schemas.py` | 请求/响应 schema |

---

## 10. 测试计划

### 10.1 后端

- `GET /sys/tenants/{tid}/roles/menu-tree`：仅含授权节点及祖先；空授权租户返回空树。
- 角色 create/patch：含未授权 menu_id → 400。
- `PUT tenant-admin`：超管成功；非超管 403；enabled true/false 幂等。
- `can_edit_membership_role`：工作空间管理员为 false；租户管理员为 true。

### 10.2 前端 / 手工

- 新建租户：无管理员字段；编辑租户：有管理员多选。
- 角色新建：未选租户无树；选租户后树正确；换租户 checkedKeys 裁剪。
- 用户新建（超管）：租户管理员默认成员；选管理员保存后 grant 生效。
- 用户编辑（工作空间管理员）：空间管理员只读；无租户管理员字段。

---

## 11. 实现顺序建议

1. 租户管理：新建隐藏管理员（纯前端，可独立交付）。
2. 角色管理：后端租户 menu-tree + 校验 → 前端联动。
3. 用户管理：capabilities 收窄 → 空间管理员只读 → tenant-admin API → 表单与保存编排。

---

**文档版本**：1.0（2026-07-02）
