# 移除模型供应商 load_balancing_enabled Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 从 `sys_models` 及全栈彻底移除未使用的 `load_balancing_enabled`（负载均衡）字段。

**Architecture:** Alembic `DROP COLUMN` + 同步 `schema_postgresql.sql`；后端 ORM / Pydantic / router / service 删除字段；前端 API 类型与 `ModelProvidersPage` 删除列、表单项、详情与 inline Switch；i18n 清理；`rg load_balancing` 扫尾确认零引用。

**Tech Stack:** PostgreSQL, Alembic, SQLAlchemy 2.x, FastAPI, pytest, React 18, TypeScript, Ant Design, i18next.

**Spec:** `docs/superpowers/specs/2026-06-01-remove-model-load-balancing-design.md`

---

## Scope Check

单个子系统：模型供应商 CRUD 存储与设置页 UI。不涉及 `app/llm`、`app/agent` 运行时逻辑（它们本就不读该字段）。

---

## File Structure

### Create

- `backend/alembic/versions/<rev>_drop_sys_models_load_balancing_enabled.py`
- `backend/sql/patches/2026-06-01-drop-sys-models-load-balancing-enabled.sql`

### Modify — Backend

- `backend/sql/schema_postgresql.sql`
- `backend/app/sys/model_provider/domain/db/models.py`
- `backend/app/sys/model_provider/api/schemas.py`
- `backend/app/sys/model_provider/api/router.py`
- `backend/app/sys/model_provider/service/model_provider_service.py`
- `backend/tests/test_llm_model_resolver.py`

### Modify — Frontend

- `frontend/src/api/modelProviders.ts`
- `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`
- `frontend/src/i18n/locales/zh-CN.json`
- `frontend/src/i18n/locales/en.json`

### Modify — Docs（实现完成后）

- `docs/superpowers/specs/2026-06-01-remove-model-load-balancing-design.md`（状态 → 已实现 + §10 实现对照）

---

### Task 1: 数据库迁移与 ORM

**Files:**
- Create: `backend/alembic/versions/<rev>_drop_sys_models_load_balancing_enabled.py`
- Create: `backend/sql/patches/2026-06-01-drop-sys-models-load-balancing-enabled.sql`
- Modify: `backend/sql/schema_postgresql.sql`
- Modify: `backend/app/sys/model_provider/domain/db/models.py`

- [ ] **Step 1: 创建 Alembic revision**

在 `backend/` 目录生成 revision（文件名中的 `<rev>` 以 `alembic revision` 输出为准）：

```python
"""drop sys_models.load_balancing_enabled

Revision ID: <rev>
Revises: c5d6e7f8a9b0
Create Date: 2026-06-01

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "<rev>"
down_revision: Union[str, Sequence[str], None] = "c5d6e7f8a9b0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("sys_models", "load_balancing_enabled")


def downgrade() -> None:
    op.add_column(
        "sys_models",
        sa.Column(
            "load_balancing_enabled",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
```

- [ ] **Step 2: 创建 SQL 补丁（开发库手工执行用）**

```sql
-- backend/sql/patches/2026-06-01-drop-sys-models-load-balancing-enabled.sql
ALTER TABLE public.sys_models
  DROP COLUMN IF EXISTS load_balancing_enabled;
```

- [ ] **Step 3: 更新 `schema_postgresql.sql`**

在 `CREATE TABLE public.sys_models` 中删除：

```sql
	load_balancing_enabled bool DEFAULT false NOT NULL,
```

删除：

```sql
COMMENT ON COLUMN public.sys_models.load_balancing_enabled IS '负载均衡';
```

- [ ] **Step 4: 删除 ORM 字段**

在 `backend/app/sys/model_provider/domain/db/models.py` 的 `SysModel` 类中删除：

```python
    load_balancing_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=sa.false()
    )
```

- [ ] **Step 5: 执行迁移（开发库）**

```bash
cd backend
alembic upgrade head
```

Expected: migration 成功，`sys_models` 无 `load_balancing_enabled` 列。

- [ ] **Step 6: Commit**

```bash
git add backend/alembic/versions/ backend/sql/ backend/app/sys/model_provider/domain/db/models.py
git commit -m "refactor(model): drop sys_models load_balancing_enabled column"
```

---

### Task 2: 后端 API 与 service

**Files:**
- Modify: `backend/app/sys/model_provider/api/schemas.py`
- Modify: `backend/app/sys/model_provider/api/router.py`
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`

- [ ] **Step 1: 删除 schemas 中的 5 处字段**

`backend/app/sys/model_provider/api/schemas.py`：

- `ModelProviderCreateIn`：删除 `load_balancing_enabled: bool = False`
- `ModelProviderPatchIn`：删除 `load_balancing_enabled: bool | None = None`
- `ModelProviderListItemOut`：删除 `load_balancing_enabled: bool`
- `ModelProviderDetailOut`：删除 `load_balancing_enabled: bool`
- `ModelProviderGroupItemOut`：删除 `load_balancing_enabled: bool`

- [ ] **Step 2: 删除 router mapper 引用**

`backend/app/sys/model_provider/api/router.py` 中删除以下 4 行（分别在 `_to_list_item`、`_to_group_item`、`_to_detail`、`_to_create_dict`）：

```python
        load_balancing_enabled=row.load_balancing_enabled,
```

```python
        "load_balancing_enabled": body.load_balancing_enabled,
```

- [ ] **Step 3: 删除 service create 写入**

`backend/app/sys/model_provider/service/model_provider_service.py` 的 `create_model` 中删除：

```python
        load_balancing_enabled=bool(data["load_balancing_enabled"]),
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/model_provider/api/schemas.py backend/app/sys/model_provider/api/router.py backend/app/sys/model_provider/service/model_provider_service.py
git commit -m "refactor(model): remove load_balancing_enabled from model provider API"
```

---

### Task 3: 后端测试

**Files:**
- Modify: `backend/tests/test_llm_model_resolver.py`

- [ ] **Step 1: 更新 `_row()` fixture**

在 `backend/tests/test_llm_model_resolver.py` 的 `_row()` 默认 `data` dict 中删除：

```python
        load_balancing_enabled=False,
```

- [ ] **Step 2: 运行相关测试**

```bash
cd backend
pytest tests/test_llm_model_resolver.py tests/test_model_provider_tags.py tests/test_model_provider_agent_models.py -v
```

Expected: 全部 PASS。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_llm_model_resolver.py
git commit -m "test: drop load_balancing_enabled from SysModel fixtures"
```

---

### Task 4: 前端 API 类型

**Files:**
- Modify: `frontend/src/api/modelProviders.ts`

- [ ] **Step 1: 删除类型字段**

从以下 3 个 type 中各删除 `load_balancing_enabled: boolean` 行：

- `ModelProviderGroupItem`
- `ModelProviderDetail`
- `ModelProviderCreateBody`

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/modelProviders.ts
git commit -m "refactor(ui): remove load_balancing_enabled from model provider types"
```

---

### Task 5: ModelProvidersPage UI

**Files:**
- Modify: `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`

- [ ] **Step 1: 删除 FormValues 字段**

```typescript
// 删除
  load_balancing_enabled: boolean
```

- [ ] **Step 2: 删除 detailToFormValues 映射**

```typescript
// 删除
    load_balancing_enabled: detail.load_balancing_enabled,
```

- [ ] **Step 3: 删除 buildPayload 字段**

```typescript
// 删除
      load_balancing_enabled: Boolean(values.load_balancing_enabled),
```

- [ ] **Step 4: 删除 openCreate 默认值**

```typescript
// 删除
      load_balancing_enabled: false,
```

- [ ] **Step 5: 删除 onSubmit patch keys 中的项**

从 `keys` 数组删除 `'load_balancing_enabled'`。

- [ ] **Step 6: 删除 handleToggleLoadBalancing 整个函数**

删除 `const handleToggleLoadBalancing = async (...) => { ... }` 整块（约 25 行）。

- [ ] **Step 7: 删除表格列定义**

删除 `columns` 数组中 `key: 'load_balancing_enabled'` 的整个 column 对象（含 Switch render）。

- [ ] **Step 8: 删除表单 Form.Item**

删除：

```tsx
          <Form.Item name="load_balancing_enabled" label={t('settings.modelProvidersFieldLb')}>
            <Select options={booleanOptions} />
          </Form.Item>
```

- [ ] **Step 9: 删除详情 Descriptions.Item**

删除：

```tsx
              <Descriptions.Item label={t('settings.modelProvidersFieldLb')}>
                {viewDetail.load_balancing_enabled ? t('common.yes') : t('common.no')}
              </Descriptions.Item>
```

- [ ] **Step 10: 可选 — 调整 tableScrollX**

将 `const tableScrollX = 1400` 改为 `1300`（删列后略减横向滚动宽度）。

- [ ] **Step 11: Commit**

```bash
git add frontend/src/features/settings/model-providers/ModelProvidersPage.tsx
git commit -m "refactor(ui): remove load balancing from model providers page"
```

---

### Task 6: i18n 清理

**Files:**
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: 删除 zh-CN 键**

删除两行：

```json
  "settings.modelProvidersColLb": "负载均衡",
```

```json
  "settings.modelProvidersFieldLb": "负载均衡",
```

- [ ] **Step 2: 删除 en 键**

删除两行：

```json
  "settings.modelProvidersColLb": "Load balancing",
```

```json
  "settings.modelProvidersFieldLb": "Load balancing",
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/i18n/locales/zh-CN.json frontend/src/i18n/locales/en.json
git commit -m "chore(i18n): remove load balancing strings for model providers"
```

---

### Task 7: 全仓扫尾与 spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-01-remove-model-load-balancing-design.md`

- [ ] **Step 1: 全仓 grep 确认零引用**

```bash
rg "load_balancing" --glob "!docs/superpowers/plans/*" --glob "!docs/superpowers/specs/2026-04-25*"
```

Expected: 无匹配（或仅剩历史归档 spec/plan 与 `health.py` 中 unrelated 注释 `load balancers`）。

若 `backend/alembic/versions/03098dd2047c_*.py` 仍含创建语句，**保留**（历史 migration 不可改）。

- [ ] **Step 2: 前端类型检查（若项目有脚本）**

```bash
cd frontend
npm run build
```

Expected: 构建成功，无 `load_balancing_enabled` 类型错误。

- [ ] **Step 3: 回填 spec 状态**

在 `docs/superpowers/specs/2026-06-01-remove-model-load-balancing-design.md` 顶部将：

```markdown
**状态**：已定稿，待实现
```

改为：

```markdown
**状态**：已实现（2026-06-01）
```

文末追加：

```markdown
## 10. 实现对照

| 项 | 代码 |
|----|------|
| Migration | `backend/alembic/versions/<rev>_drop_sys_models_load_balancing_enabled.py` |
| SQL 补丁 | `backend/sql/patches/2026-06-01-drop-sys-models-load-balancing-enabled.sql` |
| 后端 | `backend/app/sys/model_provider/` |
| 前端 | `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx` |
```

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-06-01-remove-model-load-balancing-design.md
git commit -m "docs: mark load_balancing removal spec as implemented"
```

---

## Self-Review Checklist

- [x] Spec §2 数据库 → Task 1
- [x] Spec §3 后端 → Task 2
- [x] Spec §4 前端 → Task 4 + Task 5 + Task 6
- [x] Spec §5 测试 → Task 3
- [x] Spec §6 文档 → Task 7
- [x] 无 TBD / TODO 占位
- [x] 字段名 `load_balancing_enabled` 全计划一致
