# sys_models max_tokens 字段重命名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `sys_models.max_tokens_to_sample` 全量重命名为 `max_tokens`，并同步更新 ORM、模型供应商 API、设置页 UI、Agent/规则/翻译运行时、测试及全仓文档。

**Architecture:** 单条 SQL `RENAME COLUMN` 保留数据；后端 ORM 与 Pydantic 字段统一改名；前端 `modelProviders.ts` / `ModelProvidersPage` 对齐；Agent `v2/models` 直接读 `row.max_tokens` 不再映射；最后用 `rg max_tokens_to_sample` 扫尾（**允许** SQL 补丁内 `RENAME COLUMN` 语句仍含旧列名）。

**Tech Stack:** PostgreSQL, SQLAlchemy 2.x, FastAPI, pytest, React, TypeScript, i18next.

**Spec:** `docs/superpowers/specs/2026-06-02-rename-sys-models-max-tokens-design.md`

---

## File Structure

### Create

- `backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql`

### Modify — Backend

- `backend/sql/schema_postgresql.sql`
- `backend/app/sys/model_provider/domain/db/models.py`
- `backend/app/sys/model_provider/api/schemas.py`
- `backend/app/sys/model_provider/api/router.py`
- `backend/app/sys/model_provider/service/model_provider_service.py`
- `backend/app/agent/infrastructure/chat_model_factory.py`
- `backend/app/agent/api/v2/router.py`
- `backend/app/rule/service/rule_base_service.py`
- `backend/app/translate/service/translate_llm.py`
- `backend/tests/test_agent_chat_model_factory.py`
- `backend/tests/test_agent_conversation_models_api.py`
- `backend/tests/test_llm_model_resolver.py`

### Modify — Frontend

- `frontend/src/api/modelProviders.ts`
- `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`
- `frontend/src/i18n/locales/en.json`

### Modify — Docs（全局 replace，见 Task 8）

- `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md`
- `docs/superpowers/plans/2026-06-01-agent-chat-tag-filter.md`
- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`
- `docs/superpowers/plans/2026-04-25-model-providers-crud.md`
- `docs/superpowers/plans/2026-05-28-llm-multi-capability.md`
- `docs/superpowers/plans/2026-05-23-llm-openai-compatible-runtime-unification.md`
- `docs/superpowers/specs/2026-06-02-rename-sys-models-max-tokens-design.md`（状态 → 已实现）

---

### Task 1: SQL 补丁与 schema

**Files:**
- Create: `backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 创建补丁**

```sql
-- backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql
ALTER TABLE public.sys_models
  RENAME COLUMN max_tokens_to_sample TO max_tokens;

COMMENT ON COLUMN public.sys_models.max_tokens IS '最大 token 上限';
```

- [ ] **Step 2: 更新 `schema_postgresql.sql`**

将 `sys_models` 表 DDL 中：

```sql
max_tokens_to_sample int2 NULL,
```

改为：

```sql
max_tokens int2 NULL,
```

将：

```sql
COMMENT ON COLUMN public.sys_models.max_tokens_to_sample IS '最大 token 上限';
```

改为：

```sql
COMMENT ON COLUMN public.sys_models.max_tokens IS '最大 token 上限';
```

- [ ] **Step 3: 在开发库执行补丁（可选冒烟）**

```bash
cd backend
psql "$DATABASE_URL" -f sql/patches/2026-06-02-rename-sys-models-max-tokens.sql
```

Expected: `ALTER TABLE` 成功。

- [ ] **Step 4: Commit**

```bash
git add backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql backend/sql/schema_postgresql.sql
git commit -m "chore(sql): rename sys_models.max_tokens_to_sample to max_tokens"
```

---

### Task 2: ORM

**Files:**
- Modify: `backend/app/sys/model_provider/domain/db/models.py`

- [ ] **Step 1: 改 ORM 字段**

```python
max_tokens: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/model_provider/domain/db/models.py
git commit -m "refactor(model): rename SysModel.max_tokens_to_sample to max_tokens"
```

---

### Task 3: model_provider API 层

**Files:**
- Modify: `backend/app/sys/model_provider/api/schemas.py`
- Modify: `backend/app/sys/model_provider/api/router.py`
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`

- [ ] **Step 1: schemas.py — 全局替换字段名**

将所有 `max_tokens_to_sample` 改为 `max_tokens`（5 处：CreateIn、PatchIn、ListItemOut、DetailOut、GroupItemOut）。

- [ ] **Step 2: router.py — 映射与 create dict**

```python
# _to_list_item / _to_group_item / _to_detail
max_tokens=row.max_tokens,

# _to_create_dict
"max_tokens": body.max_tokens,
```

- [ ] **Step 3: model_provider_service.py — create_model**

```python
max_tokens=data.get("max_tokens"),
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/model_provider/api/schemas.py backend/app/sys/model_provider/api/router.py backend/app/sys/model_provider/service/model_provider_service.py
git commit -m "refactor(model): expose max_tokens in model provider API"
```

---

### Task 4: 业务模块运行时

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/app/agent/api/v2/router.py`
- Modify: `backend/app/rule/service/rule_base_service.py`
- Modify: `backend/app/translate/service/translate_llm.py`

- [ ] **Step 1: chat_model_factory.py**

```python
if effective_max is None and row.max_tokens is not None:
    effective_max = row.max_tokens
```

- [ ] **Step 2: agent/v2/router.py**

```python
max_tokens=row.max_tokens,
```

- [ ] **Step 3: rule_base_service.py**

```python
mt = model_row.max_tokens
```

- [ ] **Step 4: translate_llm.py**

```python
configured_max = row.max_tokens
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/chat_model_factory.py backend/app/agent/api/v2/router.py backend/app/rule/service/rule_base_service.py backend/app/translate/service/translate_llm.py
git commit -m "refactor: read SysModel.max_tokens in agent, rule, and translate"
```

---

### Task 5: 后端测试

**Files:**
- Modify: `backend/tests/test_agent_chat_model_factory.py`
- Modify: `backend/tests/test_agent_conversation_models_api.py`
- Modify: `backend/tests/test_llm_model_resolver.py`

- [ ] **Step 1: test_agent_chat_model_factory.py**

`_model_row` 默认字典键改为 `"max_tokens": 512`。

- [ ] **Step 2: test_agent_conversation_models_api.py**

```python
row = SimpleNamespace(
    ...
    max_tokens=4096,
    ...
)
# 删除 assert "max_tokens_to_sample" not in body[0]（已无该字段）
# 保留 assert body[0]["max_tokens"] == 4096
```

- [ ] **Step 3: test_llm_model_resolver.py**

`_row(..., max_tokens=None)` 替换 `max_tokens_to_sample=None`。

- [ ] **Step 4: 运行测试**

```bash
cd backend
python -m pytest tests/test_agent_chat_model_factory.py tests/test_agent_conversation_models_api.py tests/test_llm_model_resolver.py -v
```

Expected: 全部 PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_agent_chat_model_factory.py backend/tests/test_agent_conversation_models_api.py backend/tests/test_llm_model_resolver.py
git commit -m "test: rename max_tokens_to_sample fixtures to max_tokens"
```

---

### Task 6: 前端 modelProviders + 设置页

**Files:**
- Modify: `frontend/src/api/modelProviders.ts`
- Modify: `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`

- [ ] **Step 1: modelProviders.ts**

所有类型与 body 字段 `max_tokens_to_sample` → `max_tokens`（3 处）。

- [ ] **Step 2: ModelProvidersPage.tsx**

替换以下标识符（7 处）：

- `ModelFormValues.max_tokens`
- `formValuesFromDetail`: `max_tokens: detail.max_tokens ?? null`
- `buildPayload`: `max_tokens: values.max_tokens ?? null`
- diff 字段列表: `'max_tokens'`
- `<Form.Item name="max_tokens" ...>`

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/modelProviders.ts frontend/src/features/settings/model-providers/ModelProvidersPage.tsx
git commit -m "refactor(ui): rename model provider max_tokens field"
```

---

### Task 7: i18n

**Files:**
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 更新英文标签**

```json
"settings.modelProvidersFieldMaxTokens": "Max tokens",
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/i18n/locales/en.json
git commit -m "docs(i18n): rename max tokens field label"
```

---

### Task 8: 全局文档替换

**Files:** 仓库内所有仍含 `max_tokens_to_sample` 的 `.md`（用 `rg` 列出后逐个改）

- [ ] **Step 1: 批量替换**

```bash
cd d:/ityeahProjects/minerva
rg -l max_tokens_to_sample --glob '*.md'
```

对每个文件执行 `max_tokens_to_sample` → `max_tokens`，**但**以下两处保留旧名语义：

- `backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql` 内 `RENAME COLUMN max_tokens_to_sample TO max_tokens` **不要改**
- `2026-06-02-rename-sys-models-max-tokens-design.md` 标题可保留「重命名」描述；正文迁移 SQL 块保留 `RENAME COLUMN` 原文

对 `2026-06-01-agent-chat-tag-filter-design.md` 额外修正表述：

- 「映射自 `sys_models.max_tokens_to_sample`」→「读取 `sys_models.max_tokens`」
- 「`max_tokens` ← `max_tokens_to_sample`」→「`max_tokens`（与 DB 列同名）」

- [ ] **Step 2: 更新 rename spec 状态**

`docs/superpowers/specs/2026-06-02-rename-sys-models-max-tokens-design.md`：

```markdown
**状态**：已实现（2026-06-02）
```

- [ ] **Step 3: Commit**

```bash
git add docs/
git commit -m "docs: global rename max_tokens_to_sample to max_tokens in markdown"
```

---

### Task 9: 全仓验证

- [ ] **Step 1: 代码扫描（允许 SQL 补丁含旧列名）**

```bash
rg max_tokens_to_sample --glob '!backend/sql/patches/2026-06-02-rename-sys-models-max-tokens.sql'
```

Expected: 无命中（或仅 rename spec 标题/RENAME 说明块，实现时酌情保留）。

- [ ] **Step 2: 后端回归**

```bash
cd backend
python -m pytest tests/test_agent_chat_model_factory.py tests/test_agent_conversation_models_api.py tests/test_llm_model_resolver.py tests/test_llm_domain_models.py -v
```

Expected: 全部 PASS。

- [ ] **Step 3: 前端类型检查（若项目有脚本）**

```bash
cd frontend
npm run typecheck
```

若无可用的 `typecheck` script，跳过并注明。

---

## Plan Self-Review

| Spec 要求 | Task |
|-----------|------|
| RENAME COLUMN | Task 1 |
| ORM + API | Task 2–3 |
| Agent/规则/翻译 | Task 4 |
| 前端 + i18n | Task 6–7 |
| 全局 docs | Task 8 |
| 无 API 兼容 | 无 alias Task |
| 验证 | Task 9 |

无 TBD；字段名前后均为 `max_tokens`（SQL 补丁除外）。
