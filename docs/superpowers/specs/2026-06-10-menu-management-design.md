# 菜单管理（sys_menu + 管理端 UI + 动态侧边栏）设计说明

**日期**：2026-06-10  
**状态**：已实现（2026-06-10）  
**范围**：系统全局菜单表 `sys_menu`、后端 CRUD API、设置页「菜单配置」管理界面、侧边栏从 API 动态渲染；将当前 `AppLayout` 硬编码导航种子入库。交互对齐 [RuoYi-Vue 菜单管理](https://vue.ruoyi.vip/system/menu)，字段按 Minerva 实际裁剪（**无组件路径**）。

**包路径说明**：Python 包名为 `app.sys`（与标准库 `sys` 不同）；业务代码使用 `from app.sys.menu...` 等完整限定导入。

---

## 1. 目标与成功标准

- **数据作用域**：**系统全局**单套菜单树，不按 `workspace_id` / `tenant_id` 隔离。
- **后端**：对 `sys_menu` 提供列表（树）、侧栏导航树、创建、更新、**级联删除**；删除时在应用层递归删除所有子孙节点并返回 `deleted_count`。
- **鉴权**：
  - 写操作及管理页读接口：`users.is_super_admin=true`（平台超级管理员），或在**任意租户**的 `tenant_memberships` 中为 `owner` / `admin`。
  - 侧栏导航读接口：任意已登录用户（本期不按角色过滤菜单树）。
- **前端管理页**：`/app/settings/menus`（`MenuConfigPage`）实现 RuoYi 风格树形表格 + 右侧 Drawer 表单，替换占位 `Empty`。
- **动态侧边栏**：`AppLayout` 通过 `GET /sys/menus/nav` 构建 Ant Design `Menu` items；`router.tsx` **保持静态**（仅控制展示与跳转，不动态注册路由）。
- **种子数据**：`backend/sql/seeds/sys_menu_seed.sql` 导入当前 `AppLayout` 侧栏结构（约 30+ 节点），含 `i18n_key`、`menu_key`、`path`、`icon`。
- **成功标准**：租户 owner/admin 可完成菜单 CRUD；任意登录用户侧栏与种子数据一致（除 `agents-memory` 按 `memoryBackend` 客户端过滤）；删除父节点时 Popconfirm 提示子节点数量，删除后提示共删除 N 项。

---

## 2. 数据模型

### 2.1 约定

- 主键 **UUID**；**禁止外键**；`parent_id` 逻辑引用同表 `id`，应用层维护父子与级联删除（见 minerva-conventions）。
- 同步更新 `backend/sql/schema_postgresql.sql`；已有库执行 `backend/sql/patches/2026-06-10-sys-menu.sql`（本项目以 SQL patch 增量迁移，无 `alembic/versions`）。

### 2.2 表 `sys_menu`

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| `id` | UUID | PK | 主键 |
| `parent_id` | UUID | NULL，索引 | 父节点；`NULL` 为根 |
| `menu_name` | VARCHAR(64) | NOT NULL | 管理端显示名（中文默认） |
| `i18n_key` | VARCHAR(128) | NULL | 侧栏 `t(key)`，如 `nav.overview` |
| `menu_key` | VARCHAR(64) | NULL，部分唯一 | 稳定键，对齐原 `AppLayout` Menu `key` |
| `order_num` | INT | NOT NULL DEFAULT 0 | 排序；数值越小越靠前（与 RuoYi 一致） |
| `path` | VARCHAR(256) | NULL | 路由，如 `/app/overview`；目录 M 可为空 |
| `menu_type` | CHAR(1) | NOT NULL | `M` 目录 / `C` 菜单 / `F` 按钮 |
| `perms` | VARCHAR(128) | NULL | 权限标识；`F` 必填 |
| `icon` | VARCHAR(64) | NULL | Ant Design 图标组件名，如 `BarChartOutlined` |
| `visible` | BOOLEAN | NOT NULL DEFAULT true | 是否在侧边栏显示 |
| `status` | BOOLEAN | NOT NULL DEFAULT true | 是否启用 |
| `is_external` | BOOLEAN | NOT NULL DEFAULT false | 是否外链（`true` 时 `window.open`） |
| `remark` | VARCHAR(500) | NULL | 备注 |
| `create_at` | TIMESTAMPTZ | NULL DEFAULT now() | 创建时间 |
| `update_at` | TIMESTAMPTZ | NULL | 更新时间 |

**相对 RuoYi-Vue 删除的字段**：`component`、`is_cache`、`query`、`route_name`。

**Minerva 新增字段**：`i18n_key`、`menu_key`（复用现有 i18n 与侧栏选中逻辑）。

**索引**：

- `ix_sys_menu_parent_id` ON `(parent_id)`
- `ix_sys_menu_menu_type` ON `(menu_type)`
- `uq_sys_menu_menu_key` ON `(menu_key)` WHERE `menu_key IS NOT NULL`

### 2.3 类型与父子规则

| 规则 | 说明 |
|------|------|
| `M` 目录 | 可无 `path`；子节点可为 `M` / `C` / `F` |
| `C` 菜单 | 必须有 `path`；父级只能是 `M` 或 `C` |
| `F` 按钮 | 必须有 `perms`；父级只能是 `C`；不出现在侧栏 nav |
| 防环 | 更新 `parent_id` 时不可选自身或任意后代 |
| 级联删除 | 删除节点时同一事务内删除其全部后代，再删自身 |

### 2.4 SQL 文件

| 文件 | 说明 |
|------|------|
| `backend/sql/tables/sys_menu.sql` | 建表、索引、COMMENT |
| `backend/sql/seeds/sys_menu_seed.sql` | 初始数据；固定 UUID；`ON CONFLICT (id) DO NOTHING` 幂等 |
| `backend/sql/schema_postgresql.sql` | 合并 `sys_menu` 定义 |

### 2.5 ORM 与启动建表

- 模型：`backend/app/sys/menu/domain/db/models.py` → `SysMenu`
- 在 `app/core/infrastructure/db/bootstrap.py` 的 `_import_models()` 中注册

---

## 3. 后端分层与路由

**根目录**：`backend/app/sys/menu/`

```text
app/sys/menu/
  domain/db/models.py
  infrastructure/repository.py
  service/menu_service.py
  api/schemas.py
  api/deps.py
  api/router.py
  utils/menu_tree.py
```

| 层级 | 职责 |
|------|------|
| `domain` | `SysMenu` ORM |
| `infrastructure` | 查询、写入、批量删除 |
| `service` | 校验、建树、级联删除、`deleted_count` |
| `api` | FastAPI 路由、Pydantic、`require_any_tenant_owner_or_admin` |
| `utils` | 扁平列表 → 嵌套树 |

在 `app/core/api/router.py` 中 `include_router` 挂载。

**URL 前缀**：`/sys/menus`（全局，无 `workspace_id`）

### 3.1 鉴权

新增 `require_any_tenant_owner_or_admin`（`app/sys/menu/api/deps.py` 或 `app/core/api/deps.py`）：

- 查询 `tenant_memberships`，存在 `role IN ('owner', 'admin')` 则放行
- 否则 `403` / `auth.forbidden`

### 3.2 API

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/sys/menus` | 租户 owner/admin | 管理页树；Query：`menu_name`（模糊）、`status`（bool） |
| GET | `/sys/menus/nav` | 已登录 | 侧栏树：仅 `M`+`C`，`visible=true` 且 `status=true`，按 `parent_id`、`order_num` 排序 |
| POST | `/sys/menus` | 租户 owner/admin | 创建 |
| PATCH | `/sys/menus/{id}` | 租户 owner/admin | 部分更新 |
| DELETE | `/sys/menus/{id}` | 租户 owner/admin | 级联删除；响应含 `deleted_count` |

**树节点响应字段**：`id`, `parent_id`, `menu_name`, `i18n_key`, `menu_key`, `order_num`, `path`, `menu_type`, `perms`, `icon`, `visible`, `status`, `is_external`, `remark`, `create_at`, `update_at`, `children?`

**DELETE 响应示例**：

```json
{ "deleted_count": 5 }
```

### 3.3 错误码

| 场景 | HTTP | code |
|------|------|------|
| 非租户 owner/admin | 403 | `auth.forbidden` |
| 菜单不存在 | 404 | `menu.not_found` |
| 父节点不存在 | 400 | `menu.parent_not_found` |
| 类型/父子规则违反 | 400 | `menu.invalid_hierarchy` |
| parent 成环 | 400 | `menu.cycle` |
| F 缺 perms | 400 | `menu.perms_required` |
| C 缺 path | 400 | `menu.path_required` |
| `menu_key` 重复 | 409 | `menu.conflict` |

---

## 4. 管理端 UI（MenuConfigPage）

**路由**：`/app/settings/menus`（已注册）

### 4.1 列表（对齐 RuoYi）

- 顶栏：菜单名称搜索、`状态` 筛选、**展开/折叠**、**新增**
- 树形 Table 列：菜单名称、图标、排序、权限标识、路由地址、状态、创建时间、操作
- 操作：**修改**、**新增子菜单**、**删除**（`Popconfirm`，禁止 `Modal.confirm`）

**Popconfirm 文案**：

- 标题：确定删除菜单「{menu_name}」吗？
- 描述：其下 {n} 个子菜单将一并删除，且不可恢复。（`n` 为后代数量，不含自身）

删除成功：`message.success` 显示已删除 `deleted_count` 个菜单。

### 4.2 表单（右侧 Drawer）

| 字段 | M | C | F |
|------|---|---|---|
| 上级菜单 TreeSelect | ✓ | ✓ | ✓ |
| 菜单类型 Radio | ✓ | ✓ | ✓ |
| 菜单名称 | ✓ | ✓ | ✓ |
| i18n_key | ✓ | ✓ | — |
| 图标（Input） | ✓ | ✓ | — |
| 显示排序 | ✓ | ✓ | ✓ |
| 路由 path | — | ✓ | — |
| 权限标识 perms | 可选 | 可选 | **必填** |
| 显示 visible | ✓ | ✓ | — |
| 状态 status | ✓ | ✓ | ✓ |
| 外链 is_external | — | ✓ | — |
| 备注 | ✓ | ✓ | ✓ |

非租户 owner/admin：展示无权限提示（与 API 403 一致）。

### 4.3 新增前端文件

| 文件 | 职责 |
|------|------|
| `frontend/src/api/menus.ts` | API 与类型 |
| `frontend/src/features/settings/menu-config/MenuConfigPage.tsx` | 管理页 |
| `frontend/src/features/settings/menu-config/MenuFormDrawer.tsx` | 新增/编辑抽屉 |
| `frontend/src/features/settings/menu-config/menuIconMap.ts` | 图标名 → 组件 |
| `frontend/src/app/layout/buildSiderMenuItems.tsx` | nav 树 → Menu items |

i18n：在 `zh-CN.json` / `en.json` 补充菜单管理相关键。

---

## 5. 动态侧边栏（AppLayout）

### 5.1 数据流

```
挂载 / workspaceId 就绪 → GET /sys/menus/nav → buildSiderMenuItems() → <Menu items={...} />
```

### 5.2 构建规则

1. 仅使用 API 返回的 `M` / `C` 节点
2. `label`：优先 `t(i18n_key)`，否则 `menu_name`
3. `icon`：`menuIconMap[icon]`，未知则省略或 `MenuOutlined`
4. `key`：优先 `menu_key`，否则 `id`
5. 点击：`is_external` → `window.open(path)`；否则 `nav(path)`
6. `selectedKeys` / `openKeys`：由 `resolveMenuNavState` 按当前 URL 与菜单 `path` 最长前缀匹配（`menuNavMatch.ts`）；`key` 仍为 `menu_key ?? id`；无匹配时不选中

### 5.3 特殊：智能体记忆

- 种子含 `menu_key = 'agents-memory'`
- 客户端过滤：当 `memoryBackend !== 'mem0'` 时从 nav 树剔除该项（与现 `agentSubMenuItems` 行为一致）

### 5.4 router.tsx

- **不改动**路由注册方式；新增菜单项若 `path` 无对应路由，点击后由现有 404/重定向处理

---

## 6. 种子数据（附录）

种子与当前 `AppLayout` 侧栏一致，`order_num` 按展示顺序递增。固定 UUID 在实现计划中写死（便于 `ON CONFLICT DO NOTHING`）。

| menu_key | menu_type | menu_name（种子默认） | i18n_key | path | icon | parent（menu_key） |
|----------|-----------|----------------------|----------|------|------|-------------------|
| `overview` | C | 概览 | `nav.overview` | `/app/overview` | `BarChartOutlined` | — |
| `sub-agents` | M | 智能体 | `nav.agents` | — | `RobotOutlined` | — |
| `agents-chat` | C | 对话 | `nav.agentsChat` | `/app/agents/chat` | `CommentOutlined` | `sub-agents` |
| `agents-skills` | C | 技能 | `nav.agentsSkills` | `/app/agents/skills` | `ThunderboltOutlined` | `sub-agents` |
| `agents-memory` | C | 记忆 | `nav.agentsMemory` | `/app/agents/memory` | `DatabaseOutlined` | `sub-agents` |
| `sub-doc-translate` | M | 文档翻译 | `nav.docTranslate` | — | `TranslationOutlined` | — |
| `doc-translate-translate` | C | 翻译 | `nav.docTranslateTranslate` | `/app/translate` | `FileTextOutlined` | `sub-doc-translate` |
| `sub-dataset` | M | 知识库 | `nav.knowledgeBase` | — | `ReadOutlined` | — |
| `dataset-list` | C | 数据集 | `nav.dataset` | `/app/dataset` | `UnorderedListOutlined` | `sub-dataset` |
| `sub-smart-review` | M | 智能审核 | `nav.smartReview` | — | `FileSearchOutlined` | — |
| `smart-review-text-proofreading` | C | 文本校对 | `nav.smartReviewTextProofreading` | `/app/smart-review/text-proofreading` | `FileTextOutlined` | `sub-smart-review` |
| `smart-review-text-to-text` | C | 以文审文 | `nav.smartReviewTextToText` | `/app/smart-review/review-by-text` | `AuditOutlined` | `sub-smart-review` |
| `smart-review-drawing-review` | C | 图纸审核 | `nav.smartReviewDrawingReview` | `/app/smart-review/drawing-review` | `PictureOutlined` | `sub-smart-review` |
| `sub-rules` | M | 规则 | `nav.rules` | — | `BookOutlined` | — |
| `rules-overview` | C | 概览 | `nav.rulesOverview` | `/app/rules/overview` | `DashboardOutlined` | `sub-rules` |
| `rules-mgmt-list` | C | 规则列表 | `nav.rulesManagementList` | `/app/rules/management` | `UnorderedListOutlined` | `sub-rules` |
| `sub-rules-config` | M | 配置 | `nav.rulesConfig` | — | `SlidersOutlined` | `sub-rules` |
| `rules-config-config-prompts` | C | 提示词管理 | `nav.rulesPromptManagement` | `/app/rules/config/config-prompts` | `ApiOutlined` | `sub-rules-config` |
| `sub-file-ocr` | M | 文件 OCR | `nav.rulesFileOcr` | — | `ScanOutlined` | — |
| `file-ocr-overview` | C | 概览 | `nav.rulesFileOcrOverview` | `/app/file-ocr/overview` | `DashboardOutlined` | `sub-file-ocr` |
| `file-ocr-tasks` | C | 任务列表 | `nav.rulesFileOcrTaskList` | `/app/file-ocr/tasks` | `UnorderedListOutlined` | `sub-file-ocr` |
| `sub-settings` | M | 设置 | `nav.settings` | — | `SettingOutlined` | — |
| `settings-models` | C | 模型供应商 | `settings.models` | `/app/settings/models` | `ApiOutlined` | `sub-settings` |
| `settings-ocr` | C | OCR 工具 | `settings.ocr` | `/app/settings/ocr` | `FileTextOutlined` | `sub-settings` |
| `settings-file-storage` | C | 文件存储 | `settings.fileStorage` | `/app/settings/file-storage` | `FolderOpenOutlined` | `sub-settings` |
| `settings-celery` | C | 任务调度 | `settings.celery` | `/app/settings/celery` | `ClockCircleOutlined` | `sub-settings` |
| `settings-data-sources` | C | 数据源 | `settings.dataSources` | `/app/settings/data-sources` | `DatabaseOutlined` | `sub-settings` |
| `settings-menus` | C | 菜单配置 | `settings.menuConfig` | `/app/settings/menus` | `MenuOutlined` | `sub-settings` |
| `settings-users` | C | 用户管理 | `settings.users` | `/app/settings/users` | `UserOutlined` | `sub-settings` |
| `settings-roles` | C | 角色管理 | `settings.roles` | `/app/settings/roles` | `IdcardOutlined` | `sub-settings` |
| `settings-dictionary` | C | 数据字典 | `settings.dictionary` | `/app/settings/dictionary` | `TagsOutlined` | `sub-settings` |

**说明**：`router.tsx` 中尚有重定向、嵌套子路由（如 `dataset/:id/documents`）、登录页等**不进入**侧栏种子；仅导入当前侧栏可见结构。后续可在管理页手动补充 `F` 类型按钮权限行。

---

## 7. 测试

### 7.1 后端 pytest

- `list_nav_tree` 过滤 `M`/`C`、`visible`、`status`
- `delete_menu_cascade` 返回正确 `deleted_count`
- 父子类型、防环、perms/path 必填校验
- `require_any_tenant_owner_or_admin`：member 403、owner/admin 200

### 7.2 前端手动验收

1. 租户 owner/admin 打开菜单管理，树与种子一致，CRUD 正常
2. 删除含子树的目录，Popconfirm 显示子节点数，成功后提示删除总数
3. 登录后侧栏与改前一致；修改 `visible`/`status` 后侧栏通过 `notifyMenuNavRefresh()` 自动 re-fetch
4. `memoryBackend !== 'mem0'` 时不显示「记忆」
5. 非 owner/admin 无法写菜单

---

## 8. 范围外（本期不做）

- `sys_role`、`sys_role_menu`、用户-角色绑定与按角色过滤菜单
- 按钮 `F` 的前端权限指令（仅入库）
- 动态注册 `router.tsx` 路由
- 图标上传/可视化图标选择器（本期 Input 填 Ant Design 图标名）
- workspace 级菜单隔离

---

## 9. 实现对照（以代码为准，2026-06-10）

| spec 条目 | 当前代码位置 | 备注 |
|-----------|--------------|------|
| `SysMenu` ORM | `backend/app/sys/menu/domain/db/models.py` | — |
| 级联删除 | `backend/app/sys/menu/service/menu_service.py` → `delete_menu_cascade` | 应用层，无 FK |
| 租户 admin / 超管鉴权 | `deps.py` + `identity/services.is_any_tenant_owner_or_admin`（含 `is_super_admin`） | 种子 `sql/seeds/super_admin_rongda.sql` |
| API 路由 | `backend/app/sys/menu/api/router.py` | 前缀 `/sys/menus` |
| 建表/种子 SQL | `backend/sql/tables/sys_menu.sql`、`backend/sql/seeds/sys_menu_seed.sql` | 31 条种子 |
| 管理页 | `frontend/src/features/settings/menu-config/MenuConfigPage.tsx` | Popconfirm 级联删除 |
| 动态侧栏 | `frontend/src/app/layout/AppLayout.tsx` + `buildSiderMenuItems.tsx` | `agents-memory` 客户端过滤 |
| 侧栏刷新 | `frontend/src/app/menuNavRefresh.ts` | CRUD 后 `notifyMenuNavRefresh()` |
| SQL patch | `backend/sql/patches/2026-06-10-sys-menu.sql` | 已有库增量建表 |
| `menu_key` 冲突 | `menu_service._commit_or_conflict` | 409 `menu.conflict` |
| 后端测试 | `test_menu_tree.py`、`test_menu_service.py`、`test_menu_api.py`、`test_menu_tenant_auth.py` | nav 过滤、级联删、鉴权 |
| 开发代理 | `frontend/vite.config.ts` → `^/sys` 须代理到 FastAPI | 未配置时 `/sys/menus/nav` 不会到后端，侧栏恒空 |
| 空表种子 | `menu_seed.bootstrap_sys_menu_seed`（dev 启动）+ `sql/seeds/sys_menu_seed.sql` | 亦可用 `scripts/apply_menu_bootstrap.py` |
