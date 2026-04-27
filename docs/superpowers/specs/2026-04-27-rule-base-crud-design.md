# 规则库「规则列表」CRUD（`rule_base`）设计说明

**日期**：2026-04-27  
**状态**：已确认，待实现  
**范围**：后端在 **`app/sys/rule`** 按项目规范分层实现 `public.rule_base` 的列表、创建、更新、**物理删除**；前端在菜单 **规则库 → 规则列表**（路由 `/app/rules/management`）实现表格与表单，**专业**、**文档类型** 通过数据字典 **`RULE_SUBJECT`**、**`RULE_DOC_TYPE`** 下拉选择并存储字典项 **`code`**。

**包路径说明**：使用 `from app.sys.rule...` 等完整限定导入，避免与标准库或其它 `rule` 命名冲突。

---

## 1. 目标与成功标准

- **后端**：在 `workspace_id` 成员上下文中，对 `rule_base` 完成分页列表、单条创建、部分更新、按主键物理删除；所有查询/写操作均带 **`workspace_id` 隔离**。
- **前端**：替换 `RulesManagementPage` 占位，提供可滚动表格、分页（**默认每页 10 条**，与项目常量一致）、新增/编辑抽屉、删除确认；专业、文档类型为 **`Select`** 且 **`allowClear`**（与仓库 `.cursor/skills/code-comments/SKILL.md` 约定一致）；长文本字段使用 **`Input.TextArea`**。
- **字典依赖**：表单中 **专业**（`subject_code`）、**文档类型**（`document_type`）选项来自当前工作空间下 `dict_code` 分别为 **`RULE_SUBJECT`**、**`RULE_DOC_TYPE`** 的字典项（先 `listAllDicts` / 列表找到字典 id，再 `listDictItems`）；提交值与库中存 **`code`**；表格展示优先 **项名称**（`name`），必要时以 `code` 为补充展示或 tooltip。
- **删除语义**：**物理删除**（`DELETE` 行），不使用“仅改 `status`”代替删除。
- **成功标准**：成员可完成 CRUD；非成员 **403**；跨 workspace 访问他人 `id` 返回 **404**（与字典/OCR 资源不可见策略一致）；表格在数据较多时仅表体滚动、表头固定（同项目表格规范）。

---

## 2. 数据模型

### 2.1 表 `public.rule_base`（现有 DDL）

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | uuid PK | 新建由服务端生成 |
| `workspace_id` | uuid NOT NULL | 租户隔离 |
| `sequence_number` | int2 NOT NULL，默认 0 | 序号 |
| `subject_code` | varchar(64) NULL | 专业，存字典项 **code**（`RULE_SUBJECT`） |
| `serial_number` | varchar(32) NULL | 编号 |
| `document_type` | varchar(64) NULL | 文档类型，存字典项 **code**（`RULE_DOC_TYPE`） |
| `review_section` | varchar(128) NOT NULL | 校审章节 |
| `review_object` | varchar(128) NOT NULL | 校审对象 |
| `review_rules` | text NOT NULL | 校审规则 |
| `review_result` | text NOT NULL | 校审结果 |
| `status` | varchar NOT NULL | 是否有效，约定 **`Y`** / **`N`**（与列注释一致） |
| `create_at` / `update_at` | timestamptz | 服务端维护 |

### 2.2 建议的数据库加固（实现阶段与 Alembic 同步）

- 为 `rule_base.workspace_id` 增加 **`REFERENCES public.workspaces(id) ON DELETE CASCADE`**（与 `sys_*` 等表一致），避免孤儿行；**同步更新** `backend/sql/schema_postgresql.sql`。
- 若需列表按序号排序，默认 **`sequence_number` ASC，其次 `create_at` DESC**（实现计划可微调）。

### 2.3 ORM 与启动建表

- SQLAlchemy 模型置于 **`app/sys/rule/domain/db/`**（与 `dict` / `ocr` 同构）。
- 在 `app/infrastructure/db/bootstrap.py` 的模型导入处注册，保证元数据与自动建表一致。

---

## 3. 后端分层与路由

**根目录**：`backend/app/sys/rule/`

子包与数据字典 / OCR 目录范本（见同仓库 code-comments skill）一致：`domain/`、`service/`、`infrastructure/`、`api/`，各含 `__init__.py`。

| 层级 | 职责 |
|------|------|
| `domain` | 表映射、领域常量（如 `status` 合法值） |
| `service` | 列表分页、创建、更新、按 id+workspace 删除/查询 |
| `infrastructure` | 仓储/查询实现 |
| `api` | `router.py`、`schemas.py`；Pydantic 入参/出参 |

- 在 **`app/api/router.py`** 中 `include_router` 挂载本模块。
- **URL 前缀**（与现有工作空间资源一致）：**`/workspaces/{workspace_id}/rule-base`**（`rule-base` 为 kebab-case 路径段，避免与 `rules` 等歧义冲突）。

### 3.1 鉴权

- 所有端点：`Depends(get_current_user)` + `Depends(require_workspace_member)`（路径参数 `workspace_id`）。

### 3.2 分页

- 列表查询：`page` / `page_size` Query，**`page_size` 默认** `app.pagination.DEFAULT_PAGE_SIZE`；上限与字典列表一致（如 `le=100`）。

### 3.3 API 草图

| 方法 | 路径 | 行为 |
|------|------|------|
| `GET` | `/workspaces/{workspace_id}/rule-base` | 分页列表；**可选** query：如 `status`、`subject_code`、`document_type`（首版可仅 `status` 或全部，实现计划定稿） |
| `POST` | 同上 | 创建；body 与可写字段一致；服务端设 `id`、`create_at`/`update_at` |
| `PATCH` | `.../rule-base/{id}` | 部分更新；目标行须属于该 `workspace_id` |
| `DELETE` | `.../rule-base/{id}` | **物理删除**；行须属于该 `workspace_id` |

- 单条不存在的或跨 workspace：**404**。

---

## 4. 前端

### 4.1 页面与路由

- 复用现有 **`/app/rules/management`** 与 **`RulesManagementPage`**，实现列表 + 抽屉内表单；新增 **`src/api/ruleBase.ts`**（或同项目命名惯例）封装上述 REST。

### 4.2 列表列（建议）

序号、专业（**名称**）、编号、文档类型（**名称**）、校审章节、校审对象、状态、更新时间、操作（编辑、删除）。`review_rules` / `review_result` 可仅在抽屉展示或列上截断，避免表格过宽。

### 4.3 字典未配置时

- 若找不到 `RULE_SUBJECT` 或 `RULE_DOC_TYPE` 对应字典，对应 `Select` 无选项，可用 **`message.warning`** 提示在「**数据字典**」中维护，仍允许其它字段保存（`subject_code` / `document_type` 可空时与表结构一致）。

---

## 5. 测试

- 后端：新增/扩展 pytest，风格对齐 `backend/tests/test_dict_api.py`：成员可 CRUD、非成员 403、跨 workspace 访问 id 为 404、列表分页、删除后记录不存在。

---

## 6. 非本次范围

- 规则导入/导出、版本、审批流。
- `serial_number` 自动生成规则（若需，另开 spec）。
- 对 `status = N` 的行的业务含义扩展（如「仅有效参与校审」）可在智能校审模块联调时补充。

---

## 7. 自审（规格一致性）

- 已明确：**方案 A 目录**、**物理删除**、字典编码 **`RULE_SUBJECT`** / **`RULE_DOC_TYPE`**、路径前缀 **`/rule-base`**、前端落点 **`RulesManagementPage`**。
