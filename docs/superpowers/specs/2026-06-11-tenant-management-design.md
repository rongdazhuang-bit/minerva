# 租户管理（sys_tenant + sys_workspaces + 管理端 UI）设计说明

**日期**：2026-06-11  
**状态**：已实现（2026-06-11）  
**范围**：扩展身份域表 `sys_tenant`、`sys_workspaces`（status / remark / create_at / update_at）；平台超管专用 CRUD API；设置页「租户管理」列表 + 租户表单 Drawer + 工作空间 Drawer（内嵌 CRUD）。  
**依赖**：全局菜单 `sys_menu`（新增侧栏入口，排在「角色管理」之后），见 [2026-06-10-menu-management-design.md](./2026-06-10-menu-management-design.md)。

**包路径说明**：Python 包名为 `app.sys`；业务代码使用 `from app.sys.tenant...` 等完整限定导入。ORM 模型仍位于 `app.core.domain.identity.models`（`Tenant`、`Workspace`）。

**权限网关（Supersede 部分）**：租户级 entitlement、tenant 管理员 grant 与统一鉴权见 [2026-07-01-unified-permission-gateway-design.md](./2026-07-01-unified-permission-gateway-design.md)；本 spec 的超管 CRUD 基线仍有效，扩展能力以网关 spec 为准。

---

## 1. 目标与成功标准

- **数据作用域**：租户为**平台级**资源；工作空间归属租户。API **无** `workspace_id` 前缀，全局路径 `/sys/tenants`。
- **鉴权**：**仅**平台超级管理员（`sys_user.is_super_admin = true`）；非超管全部接口 `403 auth.forbidden`。
- **后端**：
  - 对 `sys_tenant` 提供分页列表、详情、创建、更新、**级联删除**。
  - 对 `sys_workspaces` 提供嵌套于租户的分页列表、详情、创建、更新、删除（**仅删工作空间行**）。
- **前端管理页**：`/app/settings/tenants`（`TenantsPage`）RuoYi 风格分页列表 + 租户右侧 Drawer；行内「工作空间」图标打开 `WorkspaceDrawer`，内嵌该租户下工作空间 CRUD；Drawer 内容区纵向滚动使用 `minerva-scrollbar-thin`。
- **成功标准**：超管可完成租户 CRUD；可从租户行打开 Drawer 管理工作空间；`slug` 唯一性约束生效；删除租户时应用层级联清理成员与工作空间；删除单个工作空间时仅删除 `sys_workspaces` 行；非超管访问页面与 API 均 403。

---

## 2. 数据模型

### 2.1 约定

- 主键 **UUID**；**禁止外键**；`tenant_id` 为逻辑引用，应用层维护关联与删除（见 minerva-conventions）。
- 时间字段命名与角色模块一致：`create_at` / `update_at`（非 `created_at`）。
- 同步更新 `backend/sql/schema_postgresql.sql`；已有库执行 `backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql`。

### 2.2 表 `sys_tenant`（扩展后）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 已有 |
| `name` | VARCHAR(200) | NOT NULL | 租户名称 |
| `slug` | VARCHAR(64) | NOT NULL | 租户标识；**全局唯一** |
| `status` | BOOLEAN | NOT NULL DEFAULT true | **新增**；true=正常，false=停用 |
| `remark` | VARCHAR(500) | NULL | **新增**；备注 |
| `create_at` | TIMESTAMPTZ | NULL DEFAULT now() | **新增** |
| `update_at` | TIMESTAMPTZ | NULL | **新增** |

**索引**（已有 + 保持）：

- `ix_sys_tenant_slug` UNIQUE ON (`slug`)

**已有行迁移默认值**：`status=true`，`create_at=COALESCE(create_at, now())`，`remark=NULL`。

### 2.3 表 `sys_workspaces`（扩展后）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 已有 |
| `tenant_id` | UUID | NOT NULL，索引 | 所属租户 |
| `name` | VARCHAR(200) | NOT NULL | 工作空间名称 |
| `slug` | VARCHAR(64) | NOT NULL | **租户内唯一** |
| `status` | BOOLEAN | NOT NULL DEFAULT true | **新增** |
| `remark` | VARCHAR(500) | NULL | **新增** |
| `create_at` | TIMESTAMPTZ | NULL DEFAULT now() | **新增** |
| `update_at` | TIMESTAMPTZ | NULL | **新增** |

**索引**（已有 + 保持）：

- `uq_sys_workspaces_tenant_slug` UNIQUE ON (`tenant_id`, `slug`)
- `ix_sys_workspaces_tenant_id` ON (`tenant_id`)

### 2.4 删除策略

**删除租户**（`DELETE /sys/tenants/{id}`，Popconfirm 二次确认）同一事务内：

1. `DELETE FROM sys_tenant_user WHERE tenant_id = ?`
2. 对该租户下每个 workspace：`DELETE FROM sys_workspace_user WHERE workspace_id = ?`
3. `DELETE FROM sys_workspaces WHERE tenant_id = ?`
4. `DELETE FROM sys_tenant WHERE id = ?`

**删除工作空间**（Drawer 内，`DELETE /sys/tenants/{tenant_id}/workspaces/{id}`，Popconfirm）：

- 仅 `DELETE FROM sys_workspaces WHERE id = ? AND tenant_id = ?`
- **不**删除 `sys_workspace_user` 及各业务模块中按 `workspace_id` 存储的数据（已知可能产生孤儿数据，本期按产品要求接受）

### 2.5 ORM

- 扩展 `backend/app/core/domain/identity/models.py` → `Tenant`、`Workspace` 增加上述字段
- 模型已在 bootstrap 注册路径中（identity 模块），**无需**新增 bootstrap 导入

### 2.6 SQL 文件

| 文件 | 说明 |
|------|------|
| `backend/sql/patches/2026-06-11-sys-tenant-mgmt.sql` | ALTER 两表增列 + COMMENT |
| `backend/sql/patches/2026-06-11-sys-tenant-menu.sql` | 菜单种子 UPSERT + 字典 order_num 调整 |
| `backend/sql/schema_postgresql.sql` | 合并完整定义 |
| `backend/sql/seeds/sys_menu_seed.sql` | 新装库完整种子（租户管理 order_num=9，字典=10） |

---

## 3. 后端分层与路由

**根目录**：`backend/app/sys/tenant/`

```text
app/sys/tenant/
  api/deps.py           # require_super_admin
  api/schemas.py
  api/router.py
  infrastructure/repository.py
  service/tenant_service.py
```

| 层级 | 职责 |
|------|------|
| `infrastructure` | 租户/工作空间按条件分页查询、写入、级联删除 |
| `service` | slug 格式与唯一性、`update_at` 维护、级联删除编排 |
| `api` | FastAPI 路由、Pydantic、`require_super_admin` |

在 `app/core/api/router.py` 中 `include_router` 挂载。

### 3.1 鉴权

新增 `require_super_admin`（`app/sys/tenant/api/deps.py`）：

- 调用 `is_super_admin_user(session, user_id=user.id)`（`app/core/domain/identity/services.py`）
- 否则 `403 auth.forbidden`

**所有**租户与工作空间管理接口（读 + 写）均依赖此 guard。

### 3.2 租户 API

**URL 前缀**：`/sys/tenants`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sys/tenants` | 分页列表；Query：`name`（模糊 ILIKE）、`status`（bool）、`page`、`page_size`；排序 `create_at DESC` |
| POST | `/sys/tenants` | 创建；body：`name`, `slug`, `status`, `remark` |
| GET | `/sys/tenants/{tenant_id}` | 详情 |
| PATCH | `/sys/tenants/{tenant_id}` | 部分更新 |
| DELETE | `/sys/tenants/{tenant_id}` | 级联删除（§2.4） |

**列表/详情字段**：`id`, `name`, `slug`, `status`, `remark`, `create_at`, `update_at`

**写操作 body 字段**：`name`, `slug`, `status`, `remark`

**分页响应**：`{ items, total, page, page_size }`；默认 `page_size=10`（`app/pagination.DEFAULT_PAGE_SIZE`）

**校验**：

- `slug` 全局唯一；冲突 → `409 tenant.conflict`
- `slug` 格式：`^[a-z0-9]([a-z0-9-]{0,62}[a-z0-9])?$`（小写字母、数字、连字符）；非法 → `400 tenant.invalid_slug`
- 租户不存在 → `404 tenant.not_found`

**创建租户**：同一事务内写入 `sys_tenant`，并创建默认工作空间（`sys_workspaces`：`name=默认工作空间`，`slug=default`，`status` 与租户一致）。

### 3.3 工作空间 API

**URL 前缀**：`/sys/tenants/{tenant_id}/workspaces`

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/sys/tenants/{tenant_id}/workspaces` | 分页列表；Query：`name`、`status`、`page`、`page_size`；排序 `create_at DESC` |
| POST | `/sys/tenants/{tenant_id}/workspaces` | 创建；body：`name`, `slug`, `status`, `remark`；服务端写入 `tenant_id` |
| GET | `/sys/tenants/{tenant_id}/workspaces/{workspace_id}` | 详情 |
| PATCH | `/sys/tenants/{tenant_id}/workspaces/{workspace_id}` | 部分更新 |
| DELETE | `/sys/tenants/{tenant_id}/workspaces/{workspace_id}` | 仅删 `sys_workspaces` 行 |

**列表/详情字段**：`id`, `tenant_id`, `name`, `slug`, `status`, `remark`, `create_at`, `update_at`

**校验**：

- `slug` 租户内唯一 → `409 workspace.conflict`
- `slug` 格式同租户 → `400 workspace.invalid_slug`
- workspace 不属于路径 `tenant_id` → `404 workspace.not_found`
- 父租户不存在 → `404 tenant.not_found`

### 3.4 错误码

| 场景 | HTTP | code |
|------|------|------|
| 非超管 | 403 | `auth.forbidden` |
| 租户不存在 | 404 | `tenant.not_found` |
| 工作空间不存在或不属于租户 | 404 | `workspace.not_found` |
| 租户 slug 冲突 | 409 | `tenant.conflict` |
| 工作空间 slug 冲突 | 409 | `workspace.conflict` |
| slug 格式非法 | 400 | `tenant.invalid_slug` / `workspace.invalid_slug` |

---

## 4. 管理端 UI（TenantsPage）

**路由**：`/app/settings/tenants`（`router.tsx` 注册；`AppBreadcrumb` 增加映射）

**文件**：

```text
frontend/src/features/settings/tenants/
  TenantsPage.tsx
  TenantsPage.css
  TenantFormDrawer.tsx
  WorkspaceDrawer.tsx
  index.ts
frontend/src/api/tenants.ts
```

### 4.1 列表（TenantsPage）

**顶栏筛选**（Form + 搜索/重置）：

- 租户名称（Input，`allowClear`）
- 状态（Select：全部 / 正常 / 停用，`allowClear`）

**表格列**：

| 列 | 说明 |
|------|------|
| 租户名称 | `name` |
| 标识 | `slug` |
| 状态 | Tag：正常 / 停用 |
| 创建时间 | `create_at` 本地化 |
| 修改时间 | `update_at` 本地化 |
| 操作 | **修改**、**删除**（Popconfirm）、**工作空间**（`ApartmentOutlined` Tooltip → WorkspaceDrawer） |

**Popconfirm 删除租户文案**：

- 标题：确定删除租户「{name}」吗？
- 描述：将同时删除该租户下的成员、工作空间及工作空间成员，不可恢复。

- 分页：默认 10 条/页（`DEFAULT_PAGE_SIZE`）
- 顶栏 **新增租户** 按钮
- 非超管：`Result 403`（首屏 `listTenants` 返回 `auth.forbidden` 时，对齐 MenuConfigPage）

### 4.2 租户表单（TenantFormDrawer）

| 字段 | 控件 | 必填 |
|------|------|------|
| 租户名称 | Input（`allowClear`） | ✓ |
| 标识 slug | Input（`allowClear`） | ✓ |
| 状态 | Radio：正常 / 停用 | ✓ |
| 备注 | TextArea（`allowClear`） | — |

创建/编辑共用右侧 Drawer。

### 4.3 工作空间 Drawer（WorkspaceDrawer）

- 触发：租户列表行「工作空间」图标
- 标题：`{tenant.name} — 工作空间`
- 宽度：`720px`
- **内容区**包裹 `minerva-scrollbar-thin`，纵向滚动（项目标准 4px 细滚动条）
- 内嵌：筛选（名称 + 状态）+ 表格 + 「新增工作空间」
- 行操作：修改 / 删除（Popconfirm）

**Popconfirm 删除工作空间文案**：

- 标题：确定删除工作空间「{name}」吗？
- 描述：仅删除工作空间记录，成员与业务数据不会自动清理。

**工作空间子表单**（内层 Drawer，字段同租户：name / slug / status / remark）

**表格列**：名称、slug、状态、创建时间、操作

### 4.4 前端约定

- 二次确认统一 **Popconfirm**（禁止 Modal.confirm）
- 文本 Input / Select 均 `allowClear`
- i18n：`settings.tenants`、`tenants.*`（zh-CN / en）

---

## 5. 菜单种子

在「设置」目录（`parent_id = 2f899ad8-d7d2-5be5-bf63-feeb426c0bb9`）下新增：

| 字段 | 值 |
|------|-----|
| menu_name | 租户管理 |
| i18n_key | `settings.tenants` |
| menu_key | `settings-tenants` |
| order_num | **9**（排在角色管理 8 之后） |
| path | `/app/settings/tenants` |
| menu_type | `C` |
| icon | `BankOutlined` |
| visible / status | true |

将「数据字典」`order_num` 从 **9** 调整为 **10**。

固定 UUID（种子幂等）：`f3e8a912-4c1d-5b6a-9e7f-2d8c4a1b0e59`（patch 与 `sys_menu_seed.sql` 一致，`ON CONFLICT (id) DO NOTHING`）。

---

## 6. 测试

| 文件 | 覆盖 |
|------|------|
| `backend/tests/test_tenant_api.py` | 非超管 403；超管租户 CRUD；slug 冲突 409；级联删除 |
| `backend/tests/test_tenant_workspace_api.py` | 嵌套 CRUD；删 workspace 仅删一行；跨 tenant 404 |

测试模式对齐 `test_role_api.py`：mock service 或内存 DB + override `require_super_admin`。

---

## 7. 实现方案说明

采用 **独立 `app/sys/tenant` 模块 + 全局 `/sys/tenants` API**（对齐 `app/sys/menu`、`app/sys/role` 分层）。未采用将全部逻辑放入 `identity` 域（职责混杂）或将工作空间 API 独立为 `/sys/workspaces`（丢失租户上下文）。

---

## 8. 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-11 | 初稿：brainstorming 确认（超管专用、Drawer 工作空间 CRUD、对称表扩展、租户级联删、工作空间仅删行、remark 字段） |
| 2026-06-12 | 创建租户时同事务创建默认工作空间（name=默认工作空间，slug=default） |
