# 租户管理页 UX 与租户菜单授权设计说明

**日期**：2026-07-01  
**状态**：已实现（2026-07-01）  
**范围**：`TenantsPage` 操作列调整；租户授权由 `feature_code` 改为 `menu_id`（表 `sys_tenant_permission`）；授权抽屉 UI 对齐角色菜单 Tree；租户管理员多选下拉。  
**依赖**：[2026-06-11-tenant-management-design.md](./2026-06-11-tenant-management-design.md)、[2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)（§3.5 由本 spec **替代**）。

---

## 1. 目标与成功标准

- **操作列**：删除图标最后，顺序为编辑 → 工作空间 → 授权 → 删除。
- **数据模型**：`sys_tenant_entitlement` 重命名为 **`sys_tenant_permission`**；`feature_code` → **`menu_id`**（UUID，逻辑引用 `sys_menu.id`）；`granted_by_user_id` → **`create_by`**。
- **授权抽屉**：菜单勾选使用与 `RoleFormDrawer` 相同的 **Tree**（全选、展开/折叠、父子联动、边框滚动区）；数据为 `menu_ids: uuid[]`；可选范围为**全量 `sys_menu` 树**（含「设置」目录及子菜单，与角色授权一致）。
- **租户管理员**：`Select` 多选，选项为当前租户 `sys_tenant_user` 成员。
- **鉴权兼容**：各模块 `make_require_feature_workspace(feature:*)` 仍可用；由已开通 `menu_id` **推导** `tenant_features`（见 §4.4）。
- **侧栏**：非超管可见菜单 = **角色菜单 ∩ 租户已开通菜单**（含祖先闭包）。
- **成功标准**：超管保存菜单授权与管理员后正确回显；关闭某模块菜单后对应 API 403；超管不受限。

---

## 2. 不在本次范围

- 不修改 `sys_user_grant.granted_by_user_id` 字段名（仅改 `sys_tenant_permission`）。
- 不抽取 `RoleFormDrawer` / 授权抽屉的公共组件（允许局部重复 UI 代码）。
- 不调整 `WorkspaceDrawer` 操作列顺序。

---

## 3. 数据模型

### 3.1 表 `sys_tenant_permission`（替代 `sys_tenant_entitlement`）

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | UUID | PK |
| `tenant_id` | UUID | NOT NULL，索引 |
| `menu_id` | UUID | NOT NULL，逻辑引用 `sys_menu.id` |
| `enabled` | BOOLEAN | NOT NULL DEFAULT true（保留，与现表一致） |
| `create_by` | UUID | NOT NULL，原 `granted_by_user_id` |
| `create_at` | TIMESTAMPTZ | |
| `update_at` | TIMESTAMPTZ | |

**索引**：`uq_sys_tenant_permission_tenant_menu` UNIQUE ON (`tenant_id`, `menu_id`)。

**ORM**：`SysTenantEntitlement` 重命名为 `SysTenantPermission`，`__tablename__ = "sys_tenant_permission"`。

### 3.2 SQL 迁移

新增 patch：`backend/sql/patches/2026-07-01-sys-tenant-permission-rename.sql`：

1. `ALTER TABLE sys_tenant_entitlement RENAME TO sys_tenant_permission`
2. `RENAME COLUMN feature_code TO menu_id`（列类型改为 UUID；见数据迁移）
3. `RENAME COLUMN granted_by_user_id TO create_by`
4. 重建唯一索引名
5. **数据迁移**：将既有 `feature_code` 行映射为对应根菜单 `menu_id`（见下表），无法映射的行删除并记日志

| 原 feature_code | 目标 menu_key | 种子 menu_id（参考） |
|-----------------|---------------|----------------------|
| `feature:agent` | `sub-agents` | `32cbc24c-39cf-58de-966a-0e3befbc3f4e` |
| `feature:dataset` | `sub-dataset` | `80cc9a4f-f39b-564e-b3ac-158afc9ab79e` |
| `feature:ocr` | `sub-file-ocr` | `497a5510-7536-58cf-bab3-f6645ae55117` |
| `feature:skills` | `agents-skills` | `bb8fdcd0-157f-5b7b-acee-636b594e7014` |
| `feature:translate` | `sub-doc-translate` | `15a93c9c-85d7-5f2c-b87e-10a0a9c4cbbb` |
| `feature:rules` | `sub-rules` | `e67eecb6-fd62-5fc1-9d2f-e3759d3d0053` |
| `feature:file_storage` | `settings-file-storage` | `28b60cc7-5537-5a1f-b9cf-6764103b8879` |

迁移实现应通过 `menu_key` 动态查 `sys_menu.id`，勿硬编码 UUID（上表仅供文档对照）。

同步更新：`backend/sql/tables/sys_tenant_permission.sql`（新文件名）、`schema_postgresql.sql`、`generate_schema_column_comments.py`。

---

## 4. 后端变更

### 4.1 API 重命名

| 原路径 | 新路径 |
|--------|--------|
| `GET /sys/tenants/{tenant_id}/entitlements` | `GET /sys/tenants/{tenant_id}/permissions` |
| `PUT /sys/tenants/{tenant_id}/entitlements` | `PUT /sys/tenants/{tenant_id}/permissions` |

**响应 / 请求体**：

```json
{ "menu_ids": ["uuid", "..."] }
```

校验：

- 每个 `menu_id` 须在 `sys_menu` 存在 → 否则 `400 tenant.invalid_menu`
- 租户不存在 → `404 tenant.not_found`
- 鉴权仍为 `require_super_admin`

`GET/PUT .../admins` **不变**。

### 4.2 新增 API

`GET /sys/tenants/{tenant_id}/users` — 见 §5.3（租户成员下拉）。

### 4.3 Service 重命名

- `entitlement_service.py` → `tenant_permission_service.py`（或保留文件名但改内部命名，以实现时仓库风格为准）
- `list_entitlements` → `list_tenant_menu_ids`
- `replace_entitlements` → `replace_tenant_permissions`（参数 `menu_ids`，写入 `create_by`）

### 4.4 Permission Gateway 兼容

**目标**：`PermissionContext.tenant_features` 仍供 `PermissionAction.feature_code` 使用，调用方（`make_require_feature_workspace` 等）**无需改动**。

**推导规则**（`authorization/repository.py`）：

1. `load_enabled_tenant_menu_ids(session, tenant_id)` → 返回 `enabled=true` 的 `menu_id` 列表。
2. `derive_tenant_features(menu_ids, menu_rows)` → 根据 `MENU_KEY_FEATURE_MAP`（常量，放 `permission_codes.py`）将已开通菜单及其**子孙节点**映射为 `feature:*` 集合。
3. `load_enabled_tenant_features` 改为上述 1+2 的包装（对外签名不变）。

`MENU_KEY_FEATURE_MAP` 初始条目（子菜单 menu_key 通过遍历树归并到所属 feature）：

| menu_key 前缀 / 键 | feature_code |
|--------------------|--------------|
| `sub-agents`, `agents-*`（除 `agents-skills`） | `feature:agent` |
| `agents-skills` | `feature:skills` |
| `sub-dataset`, `dataset-*` | `feature:dataset` |
| `sub-file-ocr`, `file-ocr-*` | `feature:ocr` |
| `sub-doc-translate`, `doc-translate-*` | `feature:translate` |
| `sub-rules`, `rules-*` | `feature:rules` |
| `settings-file-storage` | `feature:file_storage` |

未映射的菜单（如「设置」「概览」）不参与 `feature:*` 推导，仅影响侧栏可见性。

### 4.5 侧栏过滤

`list_nav_tree_for_user` 在角色过滤之后，再与租户已开通 `menu_id` 集合求交（含：若子节点开通则保留祖先路径）。

超管侧栏仍全量；超管不受 `tenant_features` 限制。

### 4.6 废弃

- 删除 `FEATURE_CODES` 作为 entitlement 写入校验；改为校验 `menu_id` 存在性。
- `FEATURE_CODES` 可保留供 feature 推导与文档对照。
- 前端 `TENANT_FEATURE_OPTIONS` 删除，改读菜单树。

---

## 5. 前端变更

### 5.1 `TenantsPage.tsx` — 操作列

| 项 | 说明 |
|----|------|
| 按钮顺序 | 编辑 → 工作空间 → 授权 → 删除（`Popconfirm`） |
| 列宽 | `140` |

### 5.2 `TenantEntitlementDrawer` → `TenantPermissionDrawer`

| 项 | 说明 |
|----|------|
| 菜单数据源 | `GET /sys/menus`（与菜单配置页、角色授权相同的全量 `sys_menu` 树，**含设置子树**） |
| 可选范围 | **方案 A**：全量菜单，不做产品模块过滤；超管可为租户开通包括「用户管理」「角色管理」「租户管理」在内的任意菜单 |
| UI | 复用 `RoleFormDrawer` 模式：`Tree` checkable、全选、展开/折叠、父子联动、边框滚动区 |
| 表单字段 | `menu_ids: string[]` |
| API | `getTenantPermissions` / `putTenantPermissions`（`frontend/src/api/tenantPermissions.ts`，可废弃 `tenantEntitlements.ts`） |
| 打开时并行加载 | permissions、admins、menu tree、tenant users |

可抽取 `buildTreeData` / `collectAllKeys` 为同目录小工具函数，或从 `RoleFormDrawer` 复制（本期不强制共享包）。

### 5.3 租户管理员多选

与初稿一致：`Select mode="multiple"`，`GET /sys/tenants/{tenant_id}/users`，label 为 `昵称 (email)`。

### 5.4 i18n

| Key | zh-CN |
|-----|-------|
| `tenants.permissions` | 授权（或保留 `tenants.entitlements` 文案为「授权」） |
| `permissions.menuLabel` | 菜单权限 |
| `permissions.adminsLabel` | 租户管理员 |
| `permissions.adminsHint` | 从该租户成员中选择一名或多名管理员 |
| `permissions.saved` | 授权已保存 |

移除/废弃 `entitlements.feature*` 与 `TENANT_FEATURE_OPTIONS` 相关文案。

---

## 6. 测试

| 文件 | 覆盖 |
|------|------|
| `test_tenant_permission_api.py` | 替换原 entitlement 测试；menu_ids CRUD；非法 menu_id 400 |
| `test_tenant_users_api.py` | 租户成员列表 |
| `test_permission_resolver.py`（或扩展现有） | menu_id → feature 推导；侧栏交集 |
| 手动 | Tree 授权保存回显；关闭 `sub-dataset` 后 dataset API 403 |

---

## 7. 实现方案说明

采用 **表语义对齐角色授权（menu_id）+ Gateway 层 feature 推导**，避免各业务模块 deps 全量改写：

- 超管对租户授权的是「可访问菜单树」，与角色授权同一抽象。
- API 级 feature 门禁通过 `menu_key → feature:*` 映射保持向后兼容。
- 侧栏双重过滤（租户 + 角色）保证菜单与 API 一致。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-07-01 | 初稿：操作列、管理员下拉、平铺 feature 勾选 |
| 2026-07-01 | **修订**：`sys_tenant_entitlement` → `sys_tenant_permission`；`feature_code` → `menu_id`；`granted_by_user_id` → `create_by`；UI 改为菜单 Tree；API `/permissions`；Gateway feature 推导 |
| 2026-07-01 | 菜单授权范围确认 **方案 A**：全量 `sys_menu` 树（含设置子树），与角色授权一致 |
| 2026-07-01 | 实现完成：分支 `feat/tenant-page-ux-permission` |
