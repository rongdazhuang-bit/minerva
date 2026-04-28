# 规则库「规则列表」`rule_base` CRUD 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 `app/sys/rule` 实现 `rule_base` 的 REST API（列表分页、创建、部分更新、物理删除，工作空间隔离），并在 `RulesManagementPage` 用表格+抽屉完成 CRUD；专业/文档类型选项来自数据字典 `RULE_SUBJECT` / `RULE_DOC_TYPE`，存 `code`，表格展示用 **name**。

**Architecture:** 与 `app/sys/dict` 同构：ORM → infrastructure 仓储/查询 → service → `api` 路由；URL 前缀 `/workspaces/{workspace_id}/rule-base`。前端通过 `useAuth` 的 `workspaceId` + 现有 `apiJson` 调用；字典与 `OcrSettingsPage` 同路径：`listAllDicts` 按 `dict_code` 取字典 id 再 `listDictItems`。

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Pydantic v2, pytest+httpx；React 18, Ant Design 6, react-i18next.

**设计依据:** `docs/superpowers/specs/2026-04-27-rule-base-crud-design.md`

---

## 文件结构（将创建 / 将修改）

| 路径 | 职责 |
|------|------|
| `backend/alembic/versions/<new>_rule_base.py` | 创建 `rule_base` 表 + `workspace_id` FK + 索引（`down_revision=f8a2c9b01e77`） |
| `backend/sql/schema_postgresql.sql` | 为 `rule_base.workspace_id` 补 `REFERENCES public.workspaces(id) ON DELETE CASCADE`（与迁移一致） |
| `backend/app/sys/rule/**` | 全部分层（同 dict/ocr 子包布局） |
| `backend/app/api/router.py` | `include_router` 挂载 `rule_base` 路由 |
| `backend/app/infrastructure/db/bootstrap.py` | `_import_models` 中 `import app.sys.rule.domain.db.models` |
| `backend/tests/test_rule_base_api.py` | 接口测试，风格对齐 `test_dict_api.py` |
| `minerva-ui/src/api/ruleBase.ts` | `listRuleBase` / `createRuleBase` / `patchRuleBase` / `deleteRuleBase` |
| `minerva-ui/src/features/workspace/rules/RulesManagementPage.tsx` | 主表格、分页、Drawer 表单、删除确认 |
| `minerva-ui/src/i18n/locales/zh-CN.json` / `en.json` | 表头、表单项、按钮、消息文案 |

> **环境说明:** 若某环境已用 `schema_postgresql.sql` 手工建过无 FK 的 `rule_base`，应先用 Alembic 版本与库一致再执行迁移；或在本任务内用迁移 **仅** `op.create_foreign_key`（不重复建表）。首版以「库中尚无 `rule_base`」的干净 `alembic upgrade head` 为主路径，冲突时在任务中改迁移为 `inspector` 分支。

---

## Task 1: Alembic 迁移 + 同步 `schema_postgresql.sql`

**Files:**

- Create: `backend/alembic/versions/<rev>_rule_base_table.py`
- Modify: `backend/sql/schema_postgresql.sql`（`rule_base` 定义补 FK 与 `ix_rule_base_workspace_id` 如有）

- [ ] **Step 1:** 在 `f8a2c9b01e77` 之上新建 revision，在 `upgrade()` 中 `op.create_table('rule_base', ...)`：列与 `2026-04-27-rule-base-crud-design.md` §2.1 及现有 DDL 类型一致；`workspace_id` → `workspaces.id` `ON DELETE CASCADE`；`op.create_index('ix_rule_base_workspace_id', 'rule_base', ['workspace_id'])`；`downgrade()` 中 `op.drop_index` + `op.drop_table`。
- [ ] **Step 2:** 在仓库根 `cd backend` 执行 `alembic upgrade head`，期望无报错；若本机已有同表，按上文「环境说明」处理。
- [ ] **Step 3:** 将 `schema_postgresql.sql` 中 `CREATE TABLE public.rule_base` 与迁移对齐，补充 `FOREIGN KEY` 子句和索引，保证评审时 DDL 与 Alembic 一致。
- [ ] **Step 4:** `git add` 上述文件后 `commit -m "db: add rule_base table and workspace FK"`。

---

## Task 2: ORM 模型

**Files:**

- Create: `backend/app/sys/rule/__init__.py`（可空或一句 docstring）
- Create: `backend/app/sys/rule/domain/__init__.py`, `domain/db/__init__.py`
- Create: `backend/app/sys/rule/domain/db/models.py`

- [ ] **Step 1:** 在 `models.py` 定义 `class RuleBase(Base): __tablename__ = "rule_base"`，列：`id` UUID PK、`workspace_id` FK `workspaces` CASCADE、`sequence_number` SmallInteger 默认 0、`subject_code/serial_number/document_type` 可选 String、`review_section`/`review_object` String NOT NULL、`review_rules`/`review_result` `Text` NOT NULL、`status` `String(8)` NOT NULL、`create_at`/`update_at` `DateTime(timezone=True)` 与 `SysDict` 风格一致（`server_default=text("now()")` 仅给 `create_at` 如 dict）。
- [ ] **Step 2:** `RuleBase` 上为 `workspace_id` 设 `index=True`（与迁移索引名一致或依赖 ORM 默认）。
- [ ] **Step 3:** Commit: `git commit -m "feat(rule): add RuleBase ORM model"`。

---

## Task 3: 注册元数据

**Files:**

- Modify: `backend/app/infrastructure/db/bootstrap.py` 内 `_import_models()`

- [ ] **Step 1:** 追加 `import app.sys.rule.domain.db.models  # noqa: F401`。
- [ ] **Step 2:** 本地起 API（或仅跑建表）确认无导入错误。Commit: `chore(db): import rule ORM in bootstrap`。

---

## Task 4: 仓储 + Service

**Files:**

- Create: `infrastructure/repository.py`, `service/rule_base_service.py`, 各 `__init__.py`

- [ ] **Step 1:** `repository` 中实现 `list_rule_base_page(session, workspace_id, page, page_size, status?, subject_code?, document_type?)` 返回 `tuple[list[RuleBase], int]`，过滤只限当前 `workspace_id`；`ORDER BY sequence_number ASC, create_at DESC NULLS LAST`（PostgreSQL 可用 `nullslast()` 或等同）；计数 `select count`。
- [ ] **Step 2:** `get_by_id_for_workspace`；`create` 填 `id`+时间戳；`update` 用 `select`+校验 workspace；`delete` 物理 `delete` 行。
- [ ] **Step 3:** `service` 薄封装调用 repository，不泄漏 Session 给路由层。Commit: `feat(rule): rule_base repository and service`。

---

## Task 5: Pydantic + Router

**Files:**

- Create: `api/schemas.py`, `api/router.py`

- [ ] **Step 1:** 定义 `RuleBaseListItemOut`（全列除敏感）、`RuleBaseListPageOut`（`items`+`total`）、`RuleBaseCreateIn` / `RuleBasePatchIn`（`Patch` 全可选）；校验 `status` 仅允许 `Y`/`N`（用 `Field`+validator 或 `Literal`）。
- [ ] **Step 2:** `router`：`GET /workspaces/{workspace_id}/rule-base` 带 `Query page` + `Query page_size=DEFAULT_PAGE_SIZE` + 可选 `status`/`subject_code`/`document_type`；`POST` 创建；`PATCH /{id}`；`DELETE /{id}`；所有端点 `get_current_user` + `require_workspace_member` + `get_db`。
- [ ] **Step 3:** 跨 workspace 或不存在 id 返回 **404**（与 `test_dict_api` 行为一致）。Commit: `feat(rule): rule_base REST API`。

---

## Task 6: 挂载主路由

**Files:**

- Modify: `backend/app/api/router.py`

- [ ] **Step 1:** `from app.sys.rule.api.router import router as rule_base_router` 与 `api.include_router(rule_base_router)`。Commit: `feat(api): mount rule_base router`。

---

## Task 7: 后端测试

**Files:**

- Create: `backend/tests/test_rule_base_api.py`

- [ ] **Step 1:** 复制 `test_dict_api.py` 的注册+双工作空间+`h1`/`h2` 头模式；注册两用户，用 `h1` `POST` 一条合法 `rule_base`（各必填列填最小非空内容，`status: "Y"`）；`GET` 列表断言 `items` 含该条且 `total` 正确；`page_size=2` 若插入多条可测分页。
- [ ] **Step 2:** `PATCH` 改 `serial_number`；`DELETE` 后 `GET` 该 id 为 404；`h2` 访问 `workspace1` 的 list **403**；`h1` 对随机 uuid `PATCH/DELETE` **404**。
- [ ] **Step 3:** `cd backend && python -m pytest tests/test_rule_base_api.py -q`，全绿后 commit: `test(rule): rule_base API`。

---

## Task 8: 前端 API 层

**Files:**

- Create: `minerva-ui/src/api/ruleBase.ts`

- [ ] **Step 1:** 定义与后端一致的 TypeScript 类型；`listRuleBase(workspaceId, { page, page_size, status?, subject_code?, document_type? })` 拼 query；`createRuleBase`/`patchRuleBase`/`deleteRuleBase` 使用 `apiJson` 与 `method`；路径 `/workspaces/${workspaceId}/rule-base`。
- [ ] **Step 2:** Commit: `feat(ui): ruleBase API client`。

---

## Task 9: 规则列表页 UI

**Files:**

- Modify: `minerva-ui/src/features/workspace/rules/RulesManagementPage.tsx`
- Create（如需）: `RulesManagementPage.css`（与 `DictionaryPage.css` 一样处理表格区滚动、sticky 表头）

- [ ] **Step 1:** 使用 `useAuth().workspaceId`；无 workspace 时 `null` 早退或 `Empty`。
- [ ] **Step 2:** 挂载时 `listAllDicts` + 找到 `dict_code === 'RULE_SUBJECT'` / `'RULE_DOC_TYPE'` 的 id，再 `listDictItems` 两次，构建 `code → name` 的 `Map`；若缺字典，各 `message.warning` 一次（中文键走 i18n）。
- [ ] **Step 3:** `Table`：`columns` 含序号、专业名、编号、文档类型名、校审章节、校审对象、状态、`update_at`、操作；`dataSource` 来自 `listRuleBase`；`pagination` 受控 `current`+`pageSize: DEFAULT_PAGE_SIZE`（`@/constants/pagination`）+`onChange` 拉数；`scroll={{ y:  }}` 与外层 `overflow` 与 skill 中表格规范一致；**禁止**给 `InputNumber` 加 `allowClear`。
- [ ] **Step 4:** 工具栏「新增」打开 `Drawer` + `Form`：`subject_code`/`document_type` 为 `Select` `allowClear`；`status` 为 `Select` 仅 `Y`/`N`；`review_rules`/`review_result` 为 `TextArea`；提交时 `createRuleBase` 或 `patchRuleBase`；编辑时 `Form` 设初值，标题区分新增/编辑。
- [ ] **Step 5:** `Popconfirm` + `deleteRuleBase`。成功后刷新列表。Commit: `feat(ui): rules management table and form`。

---

## Task 10: i18n

**Files:**

- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`, `en.json`

- [ ] **Step 1:** 为规则列表页补充键：`rules.*` 或 `rulesList.*`（表头、新增、编辑、删除确认、各字段 label、空状态文案）；**不得**在 UI 中硬编码中文（除已存在的占位键若复用可合并）。
- [ ] **Step 2:** Commit: `i18n: rules management page strings`。

---

## Task 11: 联调与收尾

- [ ] **Step 1:** 后端与前端同开，走通新增→编辑→删→翻页；确认字典未配置时仍可保存可空项。
- [ ] **Step 2:** `cd minerva-ui && npm run build && npm run lint`；`cd backend && ruff check app/sys/rule`（或全量）`&& pytest tests/test_rule_base_api.py`。
- [ ] **Step 3:** 如需要，在 `docs/superpowers/specs/2026-04-27-rule-base-crud-design.md` 文首把状态改为 **已实现** 并单开 commit；否则省略。

---

## 自我评审（对设计文档的覆盖）

| 规范要求 | 本计划对应 |
|----------|------------|
| 方案 A 目录 + `/rule-base` | Task 2–6 |
| 物理删除 | Task 4 `delete`、Task 5 `DELETE`、Task 7 断言 |
| 字典 `RULE_SUBJECT` / `RULE_DOC_TYPE`、存 `code`、表显 `name` | Task 9 |
| workspace 隔离、403/404 | Task 5、7、设计 §3.3 |
| 分页默认 10 条 | Task 5 Query + Task 9 `DEFAULT_PAGE_SIZE` |
| 表格滚动规范 | Task 9 + CSS |
| `allowClear` 于 Select | Task 9 |
| FK + `schema_postgresql.sql` | Task 1 |
| 测试风格对齐 dict | Task 7 |

**占位符检查:** 无 TBD；「若已有表」在 Task 1 有分支说明。

---

**Plan 已保存到 `docs/superpowers/plans/2026-04-27-rule-base-crud.md`。实施方式可二选一：**

1. **Subagent 驱动（推荐）** — 每步独立子任务，步间可审查，迭代快。  
2. **本会话内执行** — 用 executing-plans 式批量推进并设检查点。

你更倾向哪一种？选定后即可从 **Task 1** 起按序实现。
