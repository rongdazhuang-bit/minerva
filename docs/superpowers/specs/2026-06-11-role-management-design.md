# 角色管理（sys_role + sys_role_menu + 管理端 UI）设计说明

**日期**：2026-06-11  
**状态**：已实现（2026-06-11）  
**范围**：按 **workspace** 隔离的角色表 `sys_role`、角色-菜单关联 `sys_role_menu`、设置页「角色管理」列表 + 右侧 Drawer（菜单权限树 M/C/F）；`SYS_ROLES` 字典用于 `role_key` 列展示映射。  
**依赖**：全局菜单表 `sys_menu`（菜单定义仍为系统全局；角色勾选的是全局菜单节点 id），见 [2026-06-10-menu-management-design.md](./2026-06-10-menu-management-design.md)。

**包路径说明**：Python 包名为 `app.sys`；业务代码使用 `from app.sys.role...` 等完整限定导入。

---

## 1. 目标与成功标准

- **数据作用域**：角色及角色-菜单关联均按 **`workspace_id` 隔离**；不同 workspace 的角色数据互不可见。
- **菜单定义**：`sys_menu` 仍为**系统全局**；`sys_role_menu.menu_id` 引用全局菜单 id，表示「该 workspace 下某角色可访问哪些菜单/按钮」。
- **后端**：在当前 workspace 上下文中，对 `sys_role` 提供分页列表、详情（含 `menu_ids`）、创建、更新、删除；写操作在同一事务内维护 `sys_role_menu` 全量替换。
- **鉴权**（对齐 Celery / 模型供应商等 workspace 模块）：
  - **读**（列表、详情、菜单权限树）：当前 workspace **成员**（`require_workspace_member`）
  - **写**（创建、更新、删除）：当前 workspace **owner/admin**（`require_workspace_owner_or_admin`）
- **权限字符 `role_key`**：表单**自由输入**，在**同一 workspace 内唯一**，**不校验**数据字典；冲突返回 `409 role.conflict`。
- **`SYS_ROLES` 字典**：与角色同属 workspace；用于列表「权限字符」列展示映射（`code` → `name`），**不用于顶栏筛选**。
- **前端管理页**：`/app/settings/roles`（`RolesPage`）通过 `useAuth().workspaceId` 调用 API；RuoYi 风格分页列表 + 右侧 Drawer；菜单权限树含 **M + C + F** 全类型，支持展开/折叠、全选/全不选、父子联动（默认开启）。
- **成功标准**：workspace owner/admin 可完成本 workspace 角色 CRUD 与菜单权限配置；`role_key` 在 workspace 内唯一；跨 workspace 访问角色 id 返回 **404**；删除角色时关联 `sys_role_menu` 一并清除；workspace member 只读、非成员 403。

---

## 2. 数据模型

### 2.1 约定

- 主键 **UUID**；**禁止外键**；`role_id` / `menu_id` 为逻辑引用，应用层维护关联与删除（见 minerva-conventions）。
- 同步更新 `backend/sql/schema_postgresql.sql`；已有库执行 `backend/sql/patches/2026-06-11-sys-role.sql`。

### 2.2 表 `sys_role`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 主键 |
| `workspace_id` | UUID | NOT NULL，索引 | 所属 workspace |
| `role_name` | VARCHAR(64) | NOT NULL | 角色名称 |
| `role_key` | VARCHAR(64) | NOT NULL | 权限字符；**workspace 内唯一** |
| `role_sort` | INT | NOT NULL DEFAULT 0 | 排序；数值越小越靠前 |
| `status` | BOOLEAN | NOT NULL DEFAULT true | true=正常，false=停用 |
| `remark` | VARCHAR(500) | NULL | 备注 |
| `create_at` | TIMESTAMPTZ | NULL DEFAULT now() | 创建时间 |
| `update_at` | TIMESTAMPTZ | NULL | 更新时间 |

**索引**：

- `uq_sys_role_workspace_role_key` UNIQUE ON (`workspace_id`, `role_key`)
- `ix_sys_role_workspace_id` ON (`workspace_id`)
- `ix_sys_role_role_sort` ON (`role_sort`)

### 2.3 表 `sys_role_menu`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 主键 |
| `role_id` | UUID | NOT NULL，索引 | 逻辑引用 `sys_role.id`（role 已含 workspace 作用域） |
| `menu_id` | UUID | NOT NULL，索引 | 逻辑引用全局 `sys_menu.id` |

**索引**：

- `uq_sys_role_menu_role_menu` UNIQUE ON (`role_id`, `menu_id`)
- `ix_sys_role_menu_role_id` ON (`role_id`)
- `ix_sys_role_menu_menu_id` ON (`menu_id`)

### 2.4 删除策略

删除角色（`DELETE /workspaces/{workspace_id}/roles/{id}`）时，同一事务内：

1. 校验 `role.workspace_id == workspace_id`，否则 **404**
2. `DELETE FROM sys_role_menu WHERE role_id = ?`
3. `DELETE FROM sys_role WHERE id = ?`

### 2.5 ORM 与启动建表

- 模型：`backend/app/sys/role/domain/db/models.py` → `SysRole`、`SysRoleMenu`
- 在 `app/core/infrastructure/db/bootstrap.py` 的 `_import_models()` 中注册

### 2.6 SQL 文件

| 文件 | 说明 |
|------|------|
| `backend/sql/tables/sys_role.sql` | 建表、索引、COMMENT |
| `backend/sql/tables/sys_role_menu.sql` | 建表、索引、COMMENT |
| `backend/sql/patches/2026-06-11-sys-role.sql` | 已有库增量建表 |
| `backend/sql/schema_postgresql.sql` | 合并上述定义 |

---

## 3. 后端分层与路由

**根目录**：`backend/app/sys/role/`

```text
app/sys/role/
  domain/db/models.py
  infrastructure/repository.py
  service/role_service.py
  api/schemas.py
  api/deps.py
  api/router.py
```

| 层级 | 职责 |
|------|------|
| `domain` | `SysRole`、`SysRoleMenu` ORM |
| `infrastructure` | 按 workspace 查询、写入、批量删除关联 |
| `service` | workspace 校验、`role_key` workspace 内唯一、`menu_ids` 合法性、关联全量替换 |
| `api` | FastAPI 路由、Pydantic、`require_workspace_member` / `require_workspace_owner_or_admin` |

在 `app/core/api/router.py` 中 `include_router` 挂载。

**URL 前缀**：`/workspaces/{workspace_id}/roles`

### 3.1 鉴权

| 操作 | 依赖 |
|------|------|
| GET 列表 / 详情 / menu-tree | `require_workspace_member` |
| POST / PATCH / DELETE | `require_workspace_owner_or_admin` |

- 非 workspace 成员 → `403 auth.forbidden`
- 资源 `id` 不属于路径中 `workspace_id` → **404** `role.not_found`（避免泄漏资源存在性，对齐字典/OCR spec）

### 3.2 API

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/workspaces/{workspace_id}/roles` | 成员 | 分页列表（仅当前 workspace）；Query：`role_name`（模糊）、`status`（bool）、`role_key`（精确）；排序 `role_sort ASC, create_at DESC` |
| GET | `/workspaces/{workspace_id}/roles/menu-tree` | 成员 | 菜单权限树（M/C/F）；内部复用 `menu_service.list_menu_tree`，**不**要求租户级菜单管理权限 |
| GET | `/workspaces/{workspace_id}/roles/{id}` | 成员 | 详情 + `menu_ids: UUID[]` |
| POST | `/workspaces/{workspace_id}/roles` | owner/admin | 创建；body 含角色字段 + `menu_ids`；服务端写入 `workspace_id` |
| PATCH | `/workspaces/{workspace_id}/roles/{id}` | owner/admin | 部分更新；若 body 含 `menu_ids` 则全量替换关联 |
| DELETE | `/workspaces/{workspace_id}/roles/{id}` | owner/admin | 删角色及全部 `sys_role_menu` |

**列表项字段**：`id`, `workspace_id`, `role_name`, `role_key`, `role_sort`, `status`, `remark`, `create_at`, `update_at`

**详情额外字段**：`menu_ids`

**写操作 body 字段**：`role_name`, `role_key`, `role_sort`, `status`, `remark`, `menu_ids`（可选；创建时默认可空数组）

**分页响应**：`{ items, total, page, page_size }`；默认 `page_size=10`（`app/pagination.DEFAULT_PAGE_SIZE`）

### 3.3 菜单权限树

- Drawer 调用 **`GET /workspaces/{workspace_id}/roles/menu-tree`**（非 `GET /sys/menus`），避免 workspace 管理员因无全局菜单管理权限而无法配置角色。
- 响应结构与 `SysMenuNodeOut` 一致（含 M/C/F 全节点）。
- 保存时校验 `menu_ids` 均存在于全局 `sys_menu`；否则 `400 role.invalid_menu_ids`。

### 3.4 错误码

| 场景 | HTTP | code |
|------|------|------|
| 非 workspace 成员 | 403 | `auth.forbidden` |
| 非 workspace owner/admin 写操作 | 403 | `auth.forbidden` |
| 角色不存在或不属于该 workspace | 404 | `role.not_found` |
| 同 workspace 内 `role_key` 重复 | 409 | `role.conflict` |
| `menu_ids` 含无效 id | 400 | `role.invalid_menu_ids` |

---

## 4. 管理端 UI（RolesPage）

**路由**：`/app/settings/roles`（已注册，替换占位 `Empty`）

**上下文**：所有 API 使用 `useAuth().workspaceId`；切换 workspace 后重新加载列表与字典。

### 4.1 列表

**顶栏筛选**（Form + 搜索/重置）：

- 角色名称（Input，`allowClear`）
- 状态（Select：全部 / 正常 / 停用）

（列表顶栏**不提供**权限字符筛选；`SYS_ROLES` 字典仅用于表格「权限字符」列展示映射。）

**表格列**：

| 列 | 说明 |
|------|------|
| 角色名称 | `role_name` |
| 权限字符 | 字典匹配时 `{name}（{role_key}）`，否则 `role_key` |
| 顺序 | `role_sort` |
| 状态 | Tag：正常 / 停用 |
| 创建时间 | `create_at` 本地化 |
| 修改时间 | `update_at` 本地化 |
| 操作 | **修改**、**删除**（`Popconfirm`）；member 只读时隐藏写操作按钮 |

**Popconfirm 删除文案**：

- 标题：确定删除角色「{role_name}」吗？
- 描述：删除后不可恢复。

- 分页：默认 10 条/页（`DEFAULT_PAGE_SIZE`）
- 顶栏 **新增** 按钮（仅 owner/admin 可见或可点）
- 非成员：`Result 403`
- workspace member 无写权限：列表可读，新增/编辑/删除不可用（或按钮 disabled + tooltip）
- 当前 workspace 无 `SYS_ROLES` 字典：列表仍显示原始 `role_key`；`message.warning` 提示一次

### 4.2 表单（右侧 Drawer，对齐 RuoYi）

| 字段 | 控件 | 必填 |
|------|------|------|
| 角色名称 | Input | ✓ |
| 权限字符 | Input | ✓ |
| 角色顺序 | InputNumber | ✓ |
| 状态 | Radio：正常 / 停用 | ✓ |
| 菜单权限 | Checkbox Tree（M+C+F） | — |
| 备注 | TextArea | — |

**菜单权限树控件**（树上方）：

- **展开/折叠**
- **全选/全不选**
- **父子联动**（默认勾选；Ant Design Tree `checkStrictly={false}`）

Tree 节点 label：`menu_name`；`menu_type=F` 时在 label 后附 `(perms)`。

**数据流**：

- 打开 Drawer：`GET .../roles/menu-tree` 拉菜单树
- 编辑：`getRole(workspaceId, id)` 回填表单 + `menu_ids` → `checkedKeys`
- 提交：`POST` / `PATCH`；成功后关闭 Drawer 并刷新列表

### 4.3 新增前端文件

| 文件 | 职责 |
|------|------|
| `frontend/src/api/roles.ts` | API 与类型（均带 `workspaceId`） |
| `frontend/src/features/settings/roles/RolesPage.tsx` | 列表 + 筛选 |
| `frontend/src/features/settings/roles/RoleFormDrawer.tsx` | 新增/编辑抽屉 |
| `frontend/src/features/settings/roles/RolesPage.css` | 表格滚动等（如需） |

i18n：在 `zh-CN.json` / `en.json` 补充 `roles.*` 键。

### 4.4 `SYS_ROLES` 字典约定

- 字典编码：`SYS_ROLES`
- 与角色同属当前 **workspace**（`sys_dict.workspace_id`）
- 字典项 `code`：与 `sys_role.role_key` 对应（用于列展示，**非强制**）
- 字典项 `name`：列表「权限字符」列友好名称
- 读取路径：`listAllDicts(workspaceId)` → `SYS_ROLES` → `listDictItems`

---

## 5. 范围外（本期不做）

| 项 | 后续占位 |
|------|----------|
| `sys_user_role` 用户-角色绑定 | spec 范围外；`UsersPage` 占位文案改为「用户角色分配功能开发中」 |
| 侧栏 `GET /sys/menus/nav` 按角色过滤 | **不改 nav API**；后续在用户绑定完成后于 nav 层按 workspace 用户角色过滤 |
| 前端按钮权限指令（F 类型 perms） | 菜单关联已入库，指令后续实现 |
| **tenant 级**角色隔离 | 不在本期（本期仅 workspace 级） |
| 后端校验 `role_key` 必须存在于 `SYS_ROLES` | 明确不做 |
| workspace 级自定义菜单（非全局 `sys_menu`） | 不在本期 |

---

## 6. 测试与验收

### 6.1 后端

- 同 workspace 内 `role_key` 重复 → 409；不同 workspace 可相同 `role_key`
- 跨 workspace 访问角色 id → 404
- `menu_ids` 含不存在 id → 400
- 删除角色后 `sys_role_menu` 无残留
- workspace member 可读、写 → 403
- workspace owner/admin 可写

### 6.2 前端手动验收

1. workspace owner/admin 完成角色新增、编辑、删除
2. Drawer 菜单树 M/C/F 勾选保存后再次编辑回显一致
3. `SYS_ROLES` 字典与权限字符列展示映射正确
4. 同 workspace 内 `role_key` 重复时报错
5. 切换 workspace 后列表数据隔离
6. member 只读、非成员 403
7. 删除 Popconfirm 正常

---

## 7. 与菜单管理 spec 的关系

- [2026-06-10-menu-management-design.md](./2026-06-10-menu-management-design.md)：`sys_menu` 为**全局菜单定义**；本 spec 在 workspace 内配置「哪些全局菜单对该 workspace 的某角色可见」。
- 菜单 spec §8 曾将 `sys_role` 列为范围外；本 spec 为正式设计，实现后应回填交叉引用。

---

## 8. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-11 | 初稿：系统全局角色 |
| 2026-06-11 | **订正**：角色 + 权限按 `workspace_id` 隔离；API 改为 `/workspaces/{workspace_id}/roles`；`role_key` 改为 workspace 内唯一；新增 `roles/menu-tree` 端点；鉴权对齐 workspace 成员读 / owner-admin 写 |
| 2026-06-11 | 实现完成 |

---

## 9. 实现对照（以代码为准，2026-06-11）

| spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| `SysRole` / `SysRoleMenu` ORM | `backend/app/sys/role/domain/db/models.py` | workspace 隔离 |
| 建表 SQL | `backend/sql/tables/sys_role.sql`、`sys_role_menu.sql` | patch `2026-06-11-sys-role.sql` |
| 角色 service | `backend/app/sys/role/service/role_service.py` | menu_ids 校验、级联删 |
| API 路由 | `backend/app/sys/role/api/router.py` | 前缀 `/workspaces/{workspace_id}/roles` |
| menu-tree | 同上 `GET .../menu-tree` | 复用 `menu_service.list_menu_tree` |
| 鉴权 | `require_workspace_member` / `require_workspace_owner_or_admin` | 成员读、owner/admin 写 |
| 后端测试 | `backend/tests/test_role_service.py`、`test_role_api.py` | — |
| 前端 API | `frontend/src/api/roles.ts` | — |
| 管理页 | `frontend/src/features/settings/roles/RolesPage.tsx` | Popconfirm 删除 |
| Drawer | `frontend/src/features/settings/roles/RoleFormDrawer.tsx` | M/C/F Checkbox Tree |
| 用户管理占位 | `frontend/src/features/settings/users/UsersPage.tsx` | i18n `placeholders.userMgmt` |
