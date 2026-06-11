# 用户管理（sys_user 扩展 + sys_user_role + 管理端 UI）设计说明

**日期**：2026-06-11  
**状态**：已实现（2026-06-11）  
**范围**：按 **workspace** 隔离的用户成员管理；扩展 `sys_user` 档案字段；新建 `sys_user_role` 多角色绑定；设置页「用户管理」列表 + 右侧 Drawer（部门树选、多角色、成员资格）。  
**依赖**：
- workspace 级角色 `sys_role`，见 [2026-06-11-role-management-design.md](./2026-06-11-role-management-design.md)
- workspace 级字典 `SYS_DEPARTMENT`，见字典模块 `app/sys/dict`
- 身份域 `sys_user` / `sys_workspace_user`，见 `app/core/domain/identity/models.py`

**包路径说明**：Python 包名为 `app.sys`；业务代码使用 `from app.sys.user...` 等完整限定导入。`User` ORM 仍位于 `app.core.domain.identity.models`。

---

## 1. 目标与成功标准

- **数据作用域**：管理**当前 workspace 下的成员**（`sys_workspace_user`）；API 前缀 `/workspaces/{workspace_id}/users`。
- **用户账号**：`sys_user` 为**全局**账号；`email` **全局唯一**；新建时邮箱已存在则**拒绝**（不邀请）。
- **档案字段**（全局，存 `sys_user`）：`nickname`、`phone`（选填、填写则全局唯一）、`status`（全局启用/停用，false 禁止登录）、`remark`、`department_item_id`（可选，逻辑引用 `sys_dict_item.id`）、`update_at`。
- **成员资格**：`sys_workspace_user.role`（`owner` / `admin` / `member`），与业务角色 `sys_role` **并存**。
- **多角色**：`sys_user_role(user_id, role_id)`，0~N 个；`role_id` 须属于当前 workspace。
- **部门**：字典 `dict_code = 'SYS_DEPARTMENT'`（workspace 级）；表单 **TreeSelect**；存 `sys_user.department_item_id`；保存时校验字典项属于**当前 workspace** 的 `SYS_DEPARTMENT`。
- **密码**：创建必填（≥8 位）；编辑可选，留空不修改。
- **删除**：
  - **移出工作空间**：删 membership + 该 workspace 下 `sys_user_role`；保留 `sys_user`。
  - **删除账号**：硬删 `sys_user` 及全部 membership、`sys_user_role`、`refresh_tokens`；**平台超管**始终可执行；**workspace owner/admin** 仅当用户**仅有当前 workspace 一条 membership** 时可执行。
- **鉴权**（对齐角色模块）：
  - **读**：workspace **成员**（`require_workspace_member`）
  - **写**：workspace **owner/admin**（`require_workspace_owner_or_admin`）
- **前端**：`/app/settings/users`（`UsersPage`）RuoYi 风格分页列表 + 右侧 Drawer；二次确认统一 **Popconfirm**。
- **成功标准**：workspace owner/admin 可完成成员 CRUD、部门与多角色配置、成员资格调整；邮箱/手机号冲突返回 409；跨 workspace 访问非成员返回 404；移出/硬删策略与权限规则生效；member 只读、非成员 403。

### 1.1 部门字段全局化的影响

`department_item_id` 存于 `sys_user`（全局一份），而 `SYS_DEPARTMENT` 字典按 workspace 隔离：

- 在 workspace W 下编辑用户时，校验 `department_item_id` 属于 W 的 `SYS_DEPARTMENT`。
- 用户若属于多个 workspace，在任一 workspace 修改部门会更新全局部门。
- 列表展示时按**当前 workspace** 字典解析名称；字典项不在当前 workspace 时显示「—」。

---

## 2. 数据模型

### 2.1 约定

- 主键 **UUID**；**禁止外键**；`user_id` / `role_id` / `department_item_id` 为逻辑引用，应用层维护关联与删除（见 minerva-conventions）。
- 同步更新 `backend/sql/schema_postgresql.sql`；已有库执行 `backend/sql/patches/2026-06-11-sys-user-mgmt.sql`。

### 2.2 表 `sys_user`（扩展）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 已有 |
| `email` | VARCHAR(320) | NOT NULL，**全局唯一** | 已有；**不可通过用户管理 PATCH 修改** |
| `password_hash` | VARCHAR(255) | NOT NULL | 已有 |
| `is_super_admin` | BOOLEAN | NOT NULL DEFAULT false | 已有；**用户管理 UI 不可编辑** |
| `nickname` | VARCHAR(64) | NOT NULL | **新增** |
| `phone` | VARCHAR(20) | NULL | **新增**；选填；非 NULL 时**全局唯一** |
| `status` | BOOLEAN | NOT NULL DEFAULT true | **新增**；false=禁止登录 |
| `remark` | VARCHAR(500) | NULL | **新增** |
| `department_item_id` | UUID | NULL | **新增**；逻辑引用 `sys_dict_item.id` |
| `created_at` | TIMESTAMPTZ | NOT NULL DEFAULT now() | 已有 |
| `update_at` | TIMESTAMPTZ | NULL | **新增** |

**索引**：

- `ix_sys_user_email` UNIQUE（已有）
- `uq_sys_user_phone` UNIQUE ON (`phone`) WHERE `phone IS NOT NULL`（部分唯一索引，允许多个 NULL）

### 2.3 表 `sys_workspace_user`（不扩展部门）

沿用已有字段：`user_id`、`workspace_id`、`role`（`MembershipRole`：`owner` / `admin` / `member`）。

用户管理中的 **成员资格** 即读写此表的 `role` 字段。

### 2.4 表 `sys_user_role`（新建）

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 主键 |
| `user_id` | UUID | NOT NULL，索引 | 逻辑引用 `sys_user.id` |
| `role_id` | UUID | NOT NULL，索引 | 逻辑引用 `sys_role.id`（role 已含 `workspace_id`） |

**索引**：

- `uq_sys_user_role_user_role` UNIQUE ON (`user_id`, `role_id`)
- `ix_sys_user_role_user_id` ON (`user_id`)
- `ix_sys_user_role_role_id` ON (`role_id`)

### 2.5 删除策略

**新建用户**（`POST /workspaces/{workspace_id}/users`）同一事务内：

1. 校验邮箱/手机号/部门/角色等业务规则
2. `INSERT INTO sys_user`
3. `INSERT INTO sys_workspace_user`（`role` 与请求一致）
4. `INSERT INTO sys_tenant_user`（`tenant_id` 取自当前 workspace 所属租户，`role` 与 workspace membership 一致）
5. 写入 `sys_user_role` 关联

**移出工作空间**（`DELETE /workspaces/{workspace_id}/users/{user_id}/membership`）同一事务内：

1. 操作者不得为目标用户本人，否则 **403** `user.cannot_delete_self`
2. 校验用户为当前 workspace 成员，否则 **404**
3. `DELETE FROM sys_user_role WHERE user_id = ? AND role_id IN (SELECT id FROM sys_role WHERE workspace_id = ?)`
4. `DELETE FROM sys_workspace_user WHERE user_id = ? AND workspace_id = ?`
5. 若该用户在当前 workspace 所属 tenant 下已无其它 workspace membership，则 `DELETE FROM sys_tenant_user WHERE user_id = ? AND tenant_id = ?`

**删除账号**（`DELETE /workspaces/{workspace_id}/users/{user_id}`）同一事务内：

1. 操作者不得为目标用户本人，否则 **403** `user.cannot_delete_self`
2. 校验权限（§3.1）；否则 **403** `user.delete_forbidden`
3. `DELETE FROM sys_user_role WHERE user_id = ?`
4. `DELETE FROM sys_tenant_user WHERE user_id = ?`
5. `DELETE FROM sys_workspace_user WHERE user_id = ?`
6. `DELETE FROM refresh_tokens WHERE user_id = ?`
7. `DELETE FROM sys_user WHERE id = ?`

**硬删除权限**：

- 调用方为平台超管（`is_super_admin_user`）→ 允许
- 或调用方为当前 workspace owner/admin **且** 该用户仅有 1 条 `sys_workspace_user` 且 `workspace_id` 为当前 workspace → 允许
- 否则 **403**

### 2.6 ORM 与启动建表

- 扩展 `backend/app/core/domain/identity/models.py` → `User` 增加新列
- 新建 `backend/app/sys/user/domain/db/models.py` → `SysUserRole`（或置于 identity models，以实现时仓库惯例为准）
- 在 `app/core/infrastructure/db/bootstrap.py` 的 `_import_models()` 中注册 `SysUserRole`

### 2.7 SQL 文件

| 文件 | 说明 |
|------|------|
| `backend/sql/tables/sys_user_role.sql` | 建表、索引、COMMENT |
| `backend/sql/patches/2026-06-11-sys-user-mgmt.sql` | ALTER `sys_user` 增列 + 建 `sys_user_role` |
| `backend/sql/schema_postgresql.sql` | 合并上述定义 |

### 2.8 字典 `SYS_DEPARTMENT`

- 由管理员在字典模块按 workspace 创建（`dict_code = 'SYS_DEPARTMENT'`）。
- 本期**不强制 SQL 种子**；无字典时前端提示先去字典管理创建。
- 校验：`department_item_id` 须为当前 workspace 下 `SYS_DEPARTMENT` 字典的有效 `sys_dict_item.id`（启用态字典项即可，不额外要求 status 字段）。

---

## 3. 后端分层与路由

**根目录**：`backend/app/sys/user/`

```text
app/sys/user/
  domain/db/models.py       # SysUserRole（若独立）
  infrastructure/repository.py
  service/user_service.py
  api/schemas.py
  api/router.py
```

| 层级 | 职责 |
|------|------|
| `infrastructure` | 按 workspace 分页查成员、写入用户/成员/角色关联、级联删除 |
| `service` | 邮箱/手机唯一、`department`/`role_ids` 校验、`role_ids` 全量替换、`can_hard_delete` 计算、硬删权限、密码哈希 |
| `api` | FastAPI 路由、Pydantic、`require_workspace_member` / `require_workspace_owner_or_admin` |

在 `app/core/api/router.py` 中 `include_router` 挂载。

**URL 前缀**：`/workspaces/{workspace_id}/users`

### 3.1 鉴权

| 操作 | 依赖 |
|------|------|
| GET 列表 / 详情 / meta | `require_workspace_member` |
| POST / PATCH / DELETE membership | `require_workspace_owner_or_admin` |
| DELETE 账号（硬删） | `require_workspace_owner_or_admin` + service 层硬删权限校验（超管或 sole-membership） |

登录鉴权须尊重 `sys_user.status`：停用用户无法获取有效 access token（在 `authenticate_user` 或等价路径增加校验）。

### 3.2 用户 API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/workspaces/{workspace_id}/users` | 分页列表（仅当前 workspace 成员） |
| GET | `/workspaces/{workspace_id}/users/{user_id}` | 详情 |
| POST | `/workspaces/{workspace_id}/users` | 新建用户并加入 workspace |
| PATCH | `/workspaces/{workspace_id}/users/{user_id}` | 更新档案、成员资格、部门、角色 |
| DELETE | `/workspaces/{workspace_id}/users/{user_id}/membership` | 移出工作空间 |
| DELETE | `/workspaces/{workspace_id}/users/{user_id}` | 硬删除全局账号 |
| GET | `/workspaces/{workspace_id}/users/meta/departments` | `SYS_DEPARTMENT` 字典项树 |
| GET | `/workspaces/{workspace_id}/users/meta/roles` | 当前 workspace 启用中的 `sys_role` 列表 |

**列表 Query**：`email`（模糊）、`nickname`（模糊）、`phone`（模糊）、`status`（bool）、`membership_role`（`owner`/`admin`/`member`）、`role_id`（UUID，筛选拥有该角色的用户）、`page`、`page_size`

**排序**：`created_at DESC`

**列表项字段**：`id`, `email`, `nickname`, `phone`, `status`, `remark`, `department_item_id`, `department_name`（服务端按当前 workspace 字典解析，无则 null）, `membership_role`, `role_ids`, `role_names`, `created_at`, `update_at`, `can_hard_delete`

**详情字段**：同列表项 + 完整 `role_ids`；编辑回填用。

**创建 body**：

```json
{
  "email": "user@example.com",
  "password": "至少8位",
  "nickname": "张三",
  "phone": "13800138000",
  "status": true,
  "remark": "",
  "membership_role": "member",
  "department_item_id": null,
  "role_ids": []
}
```

**PATCH body**（均可选，除逻辑必填外）：

`nickname`, `phone`, `status`, `remark`, `password`（留空不修改）, `membership_role`, `department_item_id`, `role_ids`（若提供则全量替换）

**分页响应**：`{ items, total, page, page_size }`；默认 `page_size=10`（`DEFAULT_PAGE_SIZE`）

### 3.3 业务规则

1. **创建**：`email` 全局已存在 → `409 user.email_taken`；`phone` 非空且已占用 → `409 user.phone_taken`；`password` 长度 < 8 → `400 user.weak_password`
2. **创建事务**：INSERT `sys_user` → INSERT `sys_workspace_user` → INSERT `sys_user_role`（可为空）
3. **更新**：目标用户非当前 workspace 成员 → `404 user.not_found`；`email` 不可改
4. **`role_ids`**：须全部属于当前 workspace 且对应 `sys_role.status = true`；否则 `400 user.role_invalid`
5. **`department_item_id`**：非 null 时须属于当前 workspace 的 `SYS_DEPARTMENT`；否则 `400 user.department_invalid`；null 表示清空部门
6. **`can_hard_delete`**：列表/详情由 service 计算——超管请求者为 true；或 owner/admin 请求者且目标用户 workspace membership 计数为 1 且为当前 workspace

### 3.4 meta 端点

**departments**：返回与字典项树一致的结构（`id`, `parent_uuid`, `code`, `name`, `children`），仅含 `SYS_DEPARTMENT`；字典不存在时返回 `[]`。

**roles**：`[{ id, role_name, role_key, status }]`，默认仅 `status=true`。

### 3.5 错误码

| 场景 | HTTP | code |
|------|------|------|
| 非 workspace 成员 | 403 | `auth.forbidden` |
| 非 owner/admin 写操作 | 403 | `auth.forbidden` |
| 用户非当前 workspace 成员 | 404 | `user.not_found` |
| 邮箱已注册 | 409 | `user.email_taken` |
| 手机号已占用 | 409 | `user.phone_taken` |
| 删除/移出本人 | 403 | `user.cannot_delete_self` |
| 无硬删除权限 | 403 | `user.delete_forbidden` |
| 部门字典项无效 | 400 | `user.department_invalid` |
| 角色 id 无效 | 400 | `user.role_invalid` |
| 密码过短 | 400 | `user.weak_password` |

---

## 4. 管理端 UI（UsersPage）

**路由**：`/app/settings/users`（已注册，替换占位 `Empty`）

**上下文**：所有 API 使用 `useAuth().workspaceId`；切换 workspace 后重新加载。

**UI 基准（硬性）**：列表、Drawer、滚动条、二次确认、分页、表单控件**必须**对齐现项目设置模块标准，以 **`RolesPage` / `RoleFormDrawer`** 为首选范本，**`TenantsPage` / `TenantFormDrawer`** 为辅助参照；不得自创新布局或滚动条尺寸。细则见 §4.4。

### 4.1 列表

**顶栏筛选**（Form + 搜索/重置，`allowClear`）：

- 邮箱、昵称、手机号（Input）
- 状态（Select：全部 / 正常 / 停用）
- 成员资格（Select：全部 / owner / admin / member）
- 角色（Select：meta/roles 下拉）

**表格列**：邮箱、昵称、手机号、部门名称、成员资格 Tag、角色多 Tag、状态 Tag、创建时间、操作

**操作列**（仅 `isWorkspaceManager`）：

| 操作 | 确认 | API |
|------|------|-----|
| 修改 | — | 打开 Drawer |
| 移出工作空间 | Popconfirm | `DELETE .../membership` |
| 删除账号 | Popconfirm（强警告） | `DELETE .../{user_id}`；仅 `can_hard_delete=true` 时显示 |

**Popconfirm 文案**：

- 移出：确定将用户「{nickname}」移出当前工作空间吗？/global 账号将保留。
- 删除账号：确定永久删除用户「{nickname}」吗？/此操作不可恢复，将删除其全局账号及全部关联数据。

- 分页：默认 10 条/页
- 顶栏 **新增**（仅 owner/admin）
- 非成员：`Result 403`
- member：列表可读，写操作隐藏

### 4.2 表单（右侧 Drawer）

| 字段 | 控件 | 新建 | 编辑 |
|------|------|------|------|
| 邮箱 | Input | 必填 | 只读 |
| 密码 | Input.Password | 必填 ≥8 | 选填，留空不改 |
| 昵称 | Input `allowClear` | 必填 | 可改 |
| 手机号 | Input `allowClear` | 选填 | 可改 |
| 状态 | Radio | 默认正常 | 可改 |
| 成员资格 | Select | 必填 | 可改 |
| 部门 | TreeSelect `allowClear` | 选填 | 可改 |
| 角色 | Select `mode="multiple"` | 选填 | 可改 |
| 备注 | TextArea | 选填 | 可改 |

- 打开 Drawer 时拉取 `meta/departments`、`meta/roles`
- 无 `SYS_DEPARTMENT` 时 `Alert` 提示

### 4.3 新增前端文件

| 文件 | 职责 |
|------|------|
| `frontend/src/api/users.ts` | API 与类型 |
| `frontend/src/features/settings/users/UsersPage.tsx` | 列表 + 筛选 |
| `frontend/src/features/settings/users/UserFormDrawer.tsx` | 新增/编辑抽屉 |
| `frontend/src/features/settings/users/UsersPage.css` | 表格滚动等 |

i18n：补充 `users.*`（`zh-CN.json` / `en.json`）；移除或保留 `placeholders.userMgmt` 不再使用。

### 4.4 UI 与交互规范（对齐现项目标准）

实现时须遵守 `code-comments` Skill 与 `minerva-conventions` Skill 中的前端约定；本节汇总用户管理模块必须落地的要点。

#### 4.4.1 分页列表（`UsersPage`）

对齐 `RolesPage` / `TenantsPage`：

| 项 | 约定 |
|----|------|
| 布局 | 根容器 `minerva-users-page`：flex 列、`height:100%`、`min-height:0`、`overflow:hidden`；`Card` + `__card` / `__header` / `__table-wrap` 分层（见 `RolesPage.css`） |
| 筛选区 | 顶栏 `Form layout="inline"`；搜索 + 重置 + 新增（owner/admin）；文本/下拉 **`allowClear`** |
| 表格 | `className="minerva-card-table-scroll-ocr"`；`rowKey="id"`；`scroll={{ x: … }}` 按列宽设置；**页面不纵向滚动**，仅表体滚动 + 表头 `sticky`（见 `code-comments`「表格滚动规则」） |
| 分页 | 初始 `pageSize` 与请求 `page_size` 均用 `DEFAULT_PAGE_SIZE`（**10**），来自 `frontend/src/constants/pagination.ts`；`showSizeChanger: true` |
| 状态展示 | `Tag` 展示状态/成员资格/角色；时间列 `toLocaleString` 格式化 |
| 权限 | 非成员 `Result 403`；`listQuery` 捕获 `auth.forbidden`；member 隐藏写操作 |
| 错误 | 列表失败 `Alert` 展示 `ApiError.message` |

#### 4.4.2 表单抽屉（`UserFormDrawer`）

对齐 `RoleFormDrawer` / `TenantFormDrawer`；**使用 Ant Design `Drawer`，禁止 `Modal` 承载主表单**：

| 项 | 约定 |
|----|------|
| 尺寸 | `width={520}`（与角色/租户表单一致） |
| 生命周期 | `destroyOnClose` |
| 滚动 | `classNames={{ body: 'minerva-scrollbar-styled' }}`（**5px** 标准滚动条） |
| 页脚 | 右对齐 `Space`：取消 + 保存（`loading={submitting}`） |
| 表单 | `layout="vertical"`；可清空字段 **`allowClear`**（`Input` / `Select` / `TreeSelect` / `TextArea`）；**不给 `InputNumber` 加 `allowClear`** |
| 多行文本 | `TextArea` 使用 `classNames={{ textarea: 'minerva-scrollbar-styled' }}` |
| 部门树 | 若内嵌可滚动树面板，容器加 `minerva-scrollbar-styled` + `maxHeight` + `overflow:auto`（同 `RoleFormDrawer` 菜单树） |

#### 4.4.3 二次确认

对齐 `minerva-conventions` §4：

- **移出工作空间**、**删除账号** 均用 **`Popconfirm`** 包裹按钮
- **禁止** `Modal.confirm` / `window.confirm`
- 删除账号使用更强警告标题与描述文案

#### 4.4.4 滚动条档位（`appLayoutScroll.css`）

| 场景 | class |
|------|-------|
| Drawer 正文、长表单、可滚动树面板 | `minerva-scrollbar-styled`（5px） |
| 表格体 | `minerva-card-table-scroll-ocr`（5px，透明轨道） |
| 嵌套小面板若需更细滚动 | `minerva-scrollbar-thin`（4px）；用户管理默认不另开第三档 |

**禁止**：业务 CSS 自定义滚动条宽度；可滚动区未挂上述 class 导致系统粗滚动条。

#### 4.4.5 后端列表分页

列表 API 默认 `page_size` 使用 `app.pagination.DEFAULT_PAGE_SIZE`（**10**），与前端一致。

#### 4.4.6 实现参照文件

| 能力 | 参照 |
|------|------|
| 列表页结构 | `frontend/src/features/settings/roles/RolesPage.tsx` + `RolesPage.css` |
| 表单抽屉 | `frontend/src/features/settings/roles/RoleFormDrawer.tsx` |
| 嵌套 Drawer 内表格 | `frontend/src/features/settings/tenants/WorkspaceDrawer.tsx` |
| 字典 TreeSelect | `frontend/src/features/settings/dictionary/DictionaryPage.tsx` |

---

## 5. 范围外（本期不做）

| 项 | 说明 |
|----|------|
| 邀请已有邮箱用户加入 workspace | 邮箱已存在则 409 拒绝 |
| `GET /sys/menus/nav` 按用户角色过滤 | **已实现**；见菜单 spec §3、`menu_service.list_nav_tree_for_user` |
| 前端按钮权限指令（F perms） | 后续 |
| 邮件/短信发送初始密码 | 后续 |
| 用户管理 UI 编辑 `is_super_admin` | 禁止 |
| 修改 `email` | 禁止 |
| tenant 级用户管理（全量） | 不在本期；超管跨租户/空间**新建**用户见 [2026-06-12-user-form-membership-tenant-design.md](./2026-06-12-user-form-membership-tenant-design.md) |

---

## 6. 测试与验收

### 6.1 后端

- 邮箱/手机号全局唯一冲突 → 409
- 非成员 / 非本 workspace 用户 → 404
- `department_item_id` / `role_ids` 校验 → 400
- 移出 workspace 后仅清除该 workspace 的 `sys_user_role`
- 硬删：超管成功；owner/admin 对多 workspace 用户 → 403
- `status=false` 用户无法登录
- member 写 → 403

### 6.2 前端手动验收

1. owner/admin 完成用户新增、编辑、移出、条件硬删
2. 部门 TreeSelect、角色多选保存后回显一致
3. 邮箱/手机冲突报错
4. `can_hard_delete` 控制「删除账号」按钮显示；当前登录用户行不显示「移出工作空间」「删除账号」
5. member 只读、切换 workspace 数据隔离
6. Popconfirm 文案与行为正确

---

## 7. 与角色管理 spec 的关系

- [2026-06-11-role-management-design.md](./2026-06-11-role-management-design.md) §5 曾将 `sys_user_role` 标为范围外；**本 spec 为正式设计**。实现后应回填角色 spec：将 `sys_user_role` 移至已实现，并更新 `UsersPage` 占位说明。

---

## 8. 修订记录

| 日期 | 变更 |
|------|------|
| 2026-06-11 | 初稿：workspace 级用户管理；方案 1；`department_item_id` 在 `sys_user`；全局 status/phone；双删除策略；A+B 硬删权限 |
| 2026-06-11 | 增补 §4.4：列表/Drawer/滚动条/Popconfirm/分页对齐 RolesPage、RoleFormDrawer 等项目标准 |
| 2026-06-11 | 实现完成 |

---

## 9. 实现对照（以代码为准，2026-06-11）

| spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| `sys_user` 扩展 | `backend/app/core/domain/identity/models.py` | nickname/phone/status/remark/department_item_id/update_at |
| `sys_user_role` ORM | `backend/app/sys/user/domain/db/models.py` | |
| 建表 SQL | `backend/sql/tables/sys_user_role.sql`、patch `2026-06-11-sys-user-mgmt.sql` | |
| user service | `backend/app/sys/user/service/user_service.py` | 校验、硬删权限、meta |
| API 路由 | `backend/app/sys/user/api/router.py` | 前缀 `/workspaces/{workspace_id}/users` |
| 登录 status | `backend/app/core/domain/identity/services.py` | `authenticate_user` |
| 前端列表/抽屉 | `frontend/src/features/settings/users/UsersPage.tsx`、`UserFormDrawer.tsx` | §4.4 UI 规范 |
| API 客户端 | `frontend/src/api/users.ts` | |
| i18n | `frontend/src/i18n/locales/zh-CN.json`、`en.json` | `users.*` |
