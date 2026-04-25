# 数据字典管理（sys_dict + sys_dict_item + 管理端 UI）设计说明

**日期**：2026-04-25  
**状态**：已评审待实现  
**范围**：后端 CRUD（代码根目录 **`app/sys/dict`**，**子目录与 `app/tool/ocr` 同构**）+ 设置页「数据字典」菜单；持久化使用现有表 `sys_dict`、`sys_dict_item`。

**包路径说明**：Python 包名为 `app.sys`（与标准库 `sys` 不同）；业务代码中应使用 **`from app.sys.dict...`** 等完整限定导入，避免与 `import sys` 混淆。

---

## 1. 目标与成功标准

- **后端**：在当前 workspace 上下文中，对数据字典主表与明细进行列表、创建、更新、删除；主从数据分别落在 `sys_dict`、`sys_dict_item`，且**按 `workspace_id` 隔离**主表数据。
- **前端**：在现有路由 `/app/settings/dictionary`（`DictionaryPage`）实现主表 + 抽屉内树形明细；仅通过 API 读写，替换占位文案。
- **主表列表排序**：`create_at DESC`，相同创建时间下 **`dict_sort DESC`**（数值越大越靠前）。
- **主表操作**：新增字典；编辑 **`dict_code`、`dict_name`、`dict_sort`**（均允许修改）；删除字典时**同时删除**关联的 `sys_dict_item`（优先由 **FK `ON DELETE CASCADE`** 保证）。
- **抽屉（明细）**：树形表格（展开/折叠）；字典项 **增 / 删 / 改**，字段含 **`code`、`name`、`item_sort`、`parent_uuid`**；**同一字典内 `code` 唯一**；删除节点时若存在子节点则 **禁止删除**。
- **成功标准**：已登录且属于路径中 `workspace_id` 的成员可完成操作；非成员 403；不同 workspace 的主表数据互不可见；跨租户访问字典或字典项 id 返回 **404**（与 OCR spec 一致，避免推断资源存在性）。

---

## 2. 数据模型与迁移

### 2.1 `sys_dict`

| 变更 | 说明 |
|------|------|
| 唯一约束 | 删除现有 **`dict_code` 单列全局唯一**；新增 **`UNIQUE (workspace_id, dict_code)`**，实现「工作空间内编码唯一」。 |
| `workspace_id` | API 写入一律带当前 workspace；迁移阶段对历史 `NULL` **回填或清理**后，目标为 **`NOT NULL`**（与 OCR workspace 模型对齐；若暂存数据无法回填，在实现计划中单列运维步骤）。 |

### 2.2 `sys_dict_item`

| 变更 | 说明 |
|------|------|
| 唯一约束 | 新增 **`UNIQUE (dict_uuid, code)`**。 |
| 外键 | **`dict_uuid` → `sys_dict(id)`，`ON DELETE CASCADE`**，删除字典时级联删除明细。 |
| `parent_uuid` | 可选 **`parent_uuid` → `sys_dict_item(id)`**（`ON DELETE` 策略与实现计划一致；业务规则为「有子节点则不可删父节点」，主要靠应用校验 + 删除前查询）。 |

### 2.3 Alembic 与 `schema_postgresql.sql`

- 新增 Alembic revision，包含上述约束与 FK；**同步更新** `backend/sql/schema_postgresql.sql`。

### 2.4 ORM 与启动建表

- SQLAlchemy 模型放在 **`backend/app/sys/dict/domain/`**（或与 ocr 对齐的具体子路径，如 `domain/db/models.py`）。
- 在 `app/infrastructure/db/bootstrap.py` 的 `_import_models()` 中注册模型，保证 `AUTO_CREATE_TABLES=true` 时元数据完整。

---

## 3. 后端分层与路由注册（对齐 `app/tool/ocr`）

**根目录**：`backend/app/sys/dict/`

与 OCR 范本一致的子包（均含 `__init__.py`）：

```text
app/sys/
  __init__.py
  dict/
    __init__.py
    domain/
    service/
    infrastructure/
    api/
    utils/
```

| 层级 | 职责 |
|------|------|
| `domain` | 实体、校验规则、领域错误约定（不依赖 FastAPI） |
| `service` | 用例编排（主表 CRUD、明细 CRUD、树/父子校验） |
| `infrastructure` | 异步 Session 持久化 |
| `api` | FastAPI 路由、Pydantic、模块内 `deps` |

- 在 **`app/api/router.py`** 中 `include_router` 挂载本模块路由。
- **URL 前缀**（与现有 OCR 风格对齐）：`/workspaces/{workspace_id}/dicts`；字典项嵌套在 **`/workspaces/{workspace_id}/dicts/{dict_id}/items`**（或等价清晰嵌套，实现计划写死）。

### 3.1 鉴权

- 所有端点：`Depends(get_current_user)` + `Depends(require_workspace_member)`（路径参数 `workspace_id`）。
- **权限**：当前 workspace 内任意已登录成员可管理本 workspace 字典（与 `require_workspace_member` 一致，不额外区分 owner/admin）。

---

## 4. API 约定（草案）

假定基础路径为 `/workspaces/{workspace_id}/dicts`。

**字典**

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/` | 当前 workspace 下字典列表；排序 `create_at DESC, dict_sort DESC` |
| POST | `/` | 创建 |
| PATCH | `/{dict_id}` | 部分更新（含 `dict_code`；违反唯一则 **409**） |
| DELETE | `/{dict_id}` | 删除字典（级联删除明细） |

**字典项**（嵌套在 `dict_id` 下）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/{dict_id}/items` | **扁平列表**（含 `parent_uuid` 等）；前端组树；校验 `dict_id` 属于当前 workspace |
| POST | `/{dict_id}/items` | 新建；校验 `code` 唯一、`parent_uuid` 属同一字典且无环 |
| PATCH | `/{dict_id}/items/{item_id}` | 更新；改 `parent_uuid` 时防环（服务端校验） |
| DELETE | `/{dict_id}/items/{item_id}` | 若有子节点 → **409 或 400**，文案明确 |

**跨 workspace**：资源不属于该 `workspace_id` 时 **404**。

---

## 5. 错误与约束

- 唯一约束冲突（`workspace_id+dict_code` 或 `dict_uuid+code`）：**409**，消息可读（必要时区分中英由 i18n/前端映射）。
- 删除有子节点的字典项：**409 或 400**，与项目现有错误风格统一。
- **`dict_code` 可改**：产品侧接受引用可能失效；UI 可对编辑编码给出简短风险提示（实现计划定文案键）。

---

## 6. 管理端 UI

- 技术栈：现有 Ant Design、`AuthContext.workspaceId`、与 OCR 页一致的 API 调用方式。
- **布局**：参考 `OcrSettingsPage`——**右侧页面不整页纵向滚动**；**仅表格体滚动 + 表头固定**；滚动条按需出现（见 `.cursor/skills/code-comments/SKILL.md` 中「OCR 工具管理页（前端）滚动规则」）。
- **主表**：列含编码、名称、排序、创建时间等；顶部 **新增字典**；行操作：**编辑**、**删除**（确认）、**字典项**（打开 **Drawer**）。
- **抽屉**：树形 `Table`；新增/编辑时使用 **下拉选择父项**（排除自身及子孙，与后端防环一致）；支持 `code`、`name`、`item_sort`、父级。
- **i18n**：更新 `zh-CN` / `en`，移除「开发中」占位。

---

## 7. 测试与验收

- **后端**：pytest 异步测试；至少覆盖：非成员 403、跨 workspace 404、列表排序、唯一约束冲突、删字典级联明细、删有子节点 item 失败、改 `parent_uuid` 成环失败（若实现环检测）。
- **手动验收**：两 workspace 数据隔离；抽屉树展开与父子下拉可用。

---

## 8. 非目标（本 spec 之后）

- 字典数据被业务模块缓存、按编码全局加载 SDK。
- 细粒度角色（仅管理员可改字典）。

---

## 9. 自检记录（spec 定稿）

- [x] 模块根路径为 **`app/sys/dict`**，结构与 **`app/tool/ocr`** 对齐。
- [x] 无未决 `TBD`：排序方向、删除策略、唯一约束范围已与需求对齐。
- [x] 多租户隔离与 404 策略与 OCR spec 一致。
- [x] 注释规约见 `.cursor/skills/code-comments/SKILL.md`。
