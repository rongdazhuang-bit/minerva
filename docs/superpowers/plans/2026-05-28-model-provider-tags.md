# 模型供应商 tags 与 Agent CHAT 过滤 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `sys_models` 增加字典驱动的 `tags` 多选字段，并在 Agent 对话选模（前端 + `ChatModelFactory`）仅允许 tag 含 `CHAT` 的模型。

**Architecture:** `tags` 以 PostgreSQL `jsonb` 存字符串数组（`MODEL_TAG` 字典 code）；`model_provider_service` 负责规范化与字典校验；现有 CRUD API 扩展入出参；Agent 在 `ChatModelFactory.from_sys_model_row` 增加 `CHAT` 校验。翻译 / `app/llm` 仍按 `model_type`，本期不改。

**Tech Stack:** FastAPI, SQLAlchemy 2.x (JSONB), pytest, React 18, Ant Design Select (multiple), TypeScript, i18next.

**Spec:** `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`

---

## Scope Check

单个子系统：`sys_models.tags` + 模型供应商管理 UI + Agent 选模过滤。不包含翻译/规则/`app/llm` 路由改造。

---

## File Structure

### Backend

- Create: `backend/app/sys/model_provider/domain/constants.py`
- Create: `backend/sql/patches/2026-05-28-sys-models-tags.sql`
- Create: `backend/tests/test_model_provider_tags.py`
- Modify: `backend/app/sys/model_provider/domain/db/models.py`
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`
- Modify: `backend/app/sys/model_provider/api/schemas.py`
- Modify: `backend/app/sys/model_provider/api/router.py`
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/tests/test_agent_chat_model_factory.py`
- Modify: `backend/tests/test_llm_model_resolver.py`（`_row()` 默认 `tags`）
- Modify: `backend/sql/schema_postgresql.sql`

### Frontend

- Modify: `frontend/src/api/modelProviders.ts`
- Modify: `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`
- Modify: `frontend/src/features/agent/AgentsPage.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

### Docs（实现完成后）

- Modify: `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`（状态 + §9 实现对照）

---

### Task 1: 数据库列与 ORM

**Files:**
- Create: `backend/app/sys/model_provider/domain/constants.py`
- Create: `backend/sql/patches/2026-05-28-sys-models-tags.sql`
- Modify: `backend/app/sys/model_provider/domain/db/models.py`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 新增常量模块**

```python
# backend/app/sys/model_provider/domain/constants.py
"""Model provider tag dictionary codes and well-known tag values."""

MODEL_TAG_DICT_CODE = "MODEL_TAG"
MODEL_TAG_CHAT = "CHAT"
```

- [ ] **Step 2: SQL 补丁（现有库）**

```sql
-- backend/sql/patches/2026-05-28-sys-models-tags.sql
ALTER TABLE public.sys_models
  ADD COLUMN IF NOT EXISTS tags jsonb NOT NULL DEFAULT '["CHAT"]'::jsonb;

COMMENT ON COLUMN public.sys_models.tags IS '模型用途标签（MODEL_TAG 字典 code 数组）';

UPDATE public.sys_models
SET tags = '["CHAT"]'::jsonb
WHERE tags IS NULL;
```

- [ ] **Step 3: 更新 `schema_postgresql.sql` 中 `CREATE TABLE sys_models`**

在 `model_config` 与 `create_at` 之间增加：

```sql
tags jsonb DEFAULT '["CHAT"]'::jsonb NOT NULL,
```

并增加 `COMMENT ON COLUMN public.sys_models.tags`。

- [ ] **Step 4: ORM 字段**

```python
# models.py 顶部增加
from sqlalchemy.dialects.postgresql import JSONB

# SysModel 类内
tags: Mapped[list[str]] = mapped_column(
    JSONB,
    nullable=False,
    server_default=sa.text("'[\"CHAT\"]'::jsonb"),
)
```

- [ ] **Step 5: 在目标库执行补丁**

Run（按项目实际 `DATABASE_URL` 配置）:

```bash
cd backend
psql "$DATABASE_URL" -f sql/patches/2026-05-28-sys-models-tags.sql
```

Expected: `ALTER TABLE` 成功，无报错。

- [ ] **Step 6: Commit**

```bash
git add backend/app/sys/model_provider/domain/constants.py \
  backend/app/sys/model_provider/domain/db/models.py \
  backend/sql/patches/2026-05-28-sys-models-tags.sql \
  backend/sql/schema_postgresql.sql
git commit -m "feat(model-provider): add sys_models.tags jsonb column"
```

---

### Task 2: tags 规范化与校验（service）

**Files:**
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`
- Create: `backend/tests/test_model_provider_tags.py`

- [ ] **Step 1: 写失败单测（规范化 + 非法 tag）**

```python
# backend/tests/test_model_provider_tags.py
"""Unit tests for MODEL_TAG validation on sys_models."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import AppError
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT, MODEL_TAG_DICT_CODE
from app.sys.model_provider.service import model_provider_service as svc


@pytest.mark.asyncio
async def test_normalize_tags_dedupes_and_sorts() -> None:
    session = AsyncMock()
    with patch.object(
        svc,
        "_load_dict_code_set",
        new=AsyncMock(return_value={"CHAT", "EMBEDDING"}),
    ):
        out = await svc.normalize_tags(
            session,
            workspace_id=uuid.uuid4(),
            tags=["EMBEDDING", "CHAT", "CHAT", "  CHAT  "],
        )
    assert out == ["CHAT", "EMBEDDING"]


@pytest.mark.asyncio
async def test_normalize_tags_rejects_empty() -> None:
    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await svc.normalize_tags(session, workspace_id=uuid.uuid4(), tags=[])
    assert exc.value.code == "model_provider.tags_required"


@pytest.mark.asyncio
async def test_normalize_tags_rejects_unknown_code() -> None:
    session = AsyncMock()
    with patch.object(
        svc,
        "_load_dict_code_set",
        new=AsyncMock(return_value={"CHAT"}),
    ):
        with pytest.raises(AppError) as exc:
            await svc.normalize_tags(
                session, workspace_id=uuid.uuid4(), tags=["CHAT", "NOPE"]
            )
    assert exc.value.code == "model_provider.tag_invalid"
```

- [ ] **Step 2: 运行单测确认失败**

Run: `cd backend && pytest tests/test_model_provider_tags.py -v`  
Expected: FAIL（`normalize_tags` 未定义）。

- [ ] **Step 3: 实现 `normalize_tags` 并在 create/update 调用**

在 `model_provider_service.py` 增加：

```python
from app.sys.model_provider.domain.constants import MODEL_TAG_DICT_CODE

async def normalize_tags(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    tags: list[str] | None,
) -> list[str]:
    """Strip, dedupe, sort, and validate tags against MODEL_TAG dictionary."""
    if not tags:
        raise AppError("model_provider.tags_required", "tags is required", 422)
    cleaned: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        code = str(raw).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        cleaned.append(code)
    if not cleaned:
        raise AppError("model_provider.tags_required", "tags is required", 422)
    allowed = await _load_dict_code_set(
        session, workspace_id=workspace_id, dict_code=MODEL_TAG_DICT_CODE
    )
    invalid = [c for c in cleaned if c not in allowed]
    if invalid:
        raise AppError(
            "model_provider.tag_invalid",
            f"Invalid tag codes: {', '.join(invalid)}",
            422,
        )
    return sorted(cleaned)
```

在 `create_model` 中、`SysModel(...)` 之前：

```python
data["tags"] = await normalize_tags(
    session, workspace_id=workspace_id, tags=data.get("tags")
)
```

并在 `SysModel(...)` 构造参数中加入 `tags=data["tags"]`。

在 `update_model` 中，若 `"tags" in patch`：

```python
patch["tags"] = await normalize_tags(
    session, workspace_id=workspace_id, tags=patch.get("tags")
)
```

- [ ] **Step 4: 运行单测通过**

Run: `cd backend && pytest tests/test_model_provider_tags.py -v`  
Expected: PASS（3 tests）。

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/model_provider/service/model_provider_service.py \
  backend/tests/test_model_provider_tags.py
git commit -m "feat(model-provider): validate MODEL_TAG tags on create/update"
```

---

### Task 3: API Schema 与 Router

**Files:**
- Modify: `backend/app/sys/model_provider/api/schemas.py`
- Modify: `backend/app/sys/model_provider/api/router.py`

- [ ] **Step 1: Schema 增加 `tags`**

`ModelProviderCreateIn`:

```python
tags: list[str] = Field(min_length=1)
```

`ModelProviderPatchIn`:

```python
tags: list[str] | None = Field(default=None, min_length=1)
```

`ModelProviderListItemOut` / `ModelProviderDetailOut` / `ModelProviderGroupItemOut`:

```python
tags: list[str]
```

- [ ] **Step 2: Router 映射**

在 `_to_list_item`、`_to_group_item`、`_to_detail` 各加 `tags=list(row.tags or [])`。

`_to_create_dict`:

```python
"tags": body.tags,
```

`_to_patch_dict` 已用 `model_dump`，确保 `tags` 键进入 `patch`（无需 strip 每项，service 会规范化）。

- [ ] **Step 3: 手动/API 冒烟（可选）**

启动 API 后 `POST /workspaces/{wid}/model-providers/models`，body 含 `"tags": ["CHAT"]`，应 201。

- [ ] **Step 4: Commit**

```bash
git add backend/app/sys/model_provider/api/schemas.py \
  backend/app/sys/model_provider/api/router.py
git commit -m "feat(model-provider): expose tags in model-providers API"
```

---

### Task 4: Agent `ChatModelFactory` CHAT 校验

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/tests/test_agent_chat_model_factory.py`

- [ ] **Step 1: 写失败测试**

在 `test_agent_chat_model_factory.py` 的 `_model_row` 默认增加 `tags=["CHAT"]`，并新增：

```python
def test_agent_chat_model_factory_rejects_missing_chat_tag() -> None:
    row, workspace_id = _model_row(tags=["EMBEDDING"])

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_tag_not_allowed"


def test_agent_chat_model_factory_accepts_chat_tag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.agent.infrastructure.chat_model_factory.AgentChatOpenAI",
        lambda **kwargs: object(),
    )
    row, workspace_id = _model_row(tags=["CHAT", "EMBEDDING"])
    ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_agent_chat_model_factory.py::test_agent_chat_model_factory_rejects_missing_chat_tag -v`  
Expected: FAIL。

- [ ] **Step 3: 实现校验**

在 `chat_model_factory.py`：

```python
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT

def _tags_include_chat(tags: object) -> bool:
    if not isinstance(tags, list):
        return False
    return MODEL_TAG_CHAT in {str(t).strip() for t in tags if t is not None}
```

在 `from_sys_model_row`，`if not row.enabled` 块之后：

```python
if not _tags_include_chat(getattr(row, "tags", None)):
    raise AppError(
        "agent.model_tag_not_allowed",
        "该模型未标记为对话用途。",
        422,
    )
```

- [ ] **Step 4: 运行 Agent factory 全文件测试**

Run: `cd backend && pytest tests/test_agent_chat_model_factory.py -v`  
Expected: 全部 PASS。

- [ ] **Step 5: 修复 `test_llm_model_resolver._row` 默认 tags**

```python
tags=["CHAT"],
```

Run: `cd backend && pytest tests/test_llm_model_resolver.py -v`  
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/infrastructure/chat_model_factory.py \
  backend/tests/test_agent_chat_model_factory.py \
  backend/tests/test_llm_model_resolver.py
git commit -m "feat(agent): require CHAT tag on ChatModelFactory"
```

---

### Task 5: 前端 API 类型

**Files:**
- Modify: `frontend/src/api/modelProviders.ts`

- [ ] **Step 1: 类型增加 `tags: string[]`**

在 `ModelProviderGroupItem`、`ModelProviderListItem`、`ModelProviderDetail`、`ModelProviderCreateBody` 增加 `tags: string[]`；`ModelProviderPatchBody` 为 `tags?: string[]`。

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/modelProviders.ts
git commit -m "feat(ui): add tags to model provider API types"
```

---

### Task 6: 模型供应商设置页 UI

**Files:**
- Modify: `frontend/src/features/settings/model-providers/ModelProvidersPage.tsx`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: i18n**

`zh-CN.json`:

```json
"settings.modelProvidersFieldTags": "标签",
"settings.modelProvidersFieldTagsRequired": "请至少选择一个标签",
"settings.modelProvidersColTags": "标签"
```

`en.json`:

```json
"settings.modelProvidersFieldTags": "Tags",
"settings.modelProvidersFieldTagsRequired": "Select at least one tag",
"settings.modelProvidersColTags": "Tags"
```

- [ ] **Step 2: 加载 `MODEL_TAG` 字典**

```typescript
const DICT_CODE_MODEL_TAG = 'MODEL_TAG'
const [tagItems, setTagItems] = useState<SysDictItem[]>([])
// 在现有 loadDicts 中 listDictItems(workspaceId, DICT_CODE_MODEL_TAG) 并入 setTagItems
```

- [ ] **Step 3: 表单**

`FormValues` 增加 `tags?: string[]`；`detailToFormValues` 增加 `tags: detail.tags ?? []`；`buildPayload` 增加 `tags: merged.tags ?? []`。

Drawer 表单（`model_type` 附近）：

```tsx
<Form.Item
  name="tags"
  label={t('settings.modelProvidersFieldTags')}
  rules={[{ required: true, message: t('settings.modelProvidersFieldTagsRequired') }]}
>
  <Select
    mode="multiple"
    options={sortDictItems(tagItems).map((i) => ({
      value: i.code,
      label: i.name ?? i.code,
    }))}
    placeholder={t('settings.modelProvidersFieldTags')}
  />
</Form.Item>
```

`onSubmit` patch 逻辑：将 `tags` 加入 `keys` 数组；用 `JSON.stringify(next.tags)` 与 `editingBase.tags` 比较决定是否写入 patch。

- [ ] **Step 4: 表格与查看**

分组表 columns 增加一列，render 多个 `DictText`（`dictCode={DICT_CODE_MODEL_TAG}`）或 `Tag`。

查看抽屉 Descriptions 增加 tags 项。

- [ ] **Step 5: 本地验证**

1. 设置 → 字典：确保有 `MODEL_TAG` + `CHAT` 项。  
2. 新增模型必选 tags；保存后列表可见。  
3. 仅选非 CHAT tag 的模型在 Agent 页不可见（Task 7）。

- [ ] **Step 6: Commit**

```bash
git add frontend/src/features/settings/model-providers/ModelProvidersPage.tsx \
  frontend/src/i18n/locales/zh-CN.json \
  frontend/src/i18n/locales/en.json
git commit -m "feat(ui): model provider tags multi-select and table column"
```

---

### Task 7: Agent 对话页过滤

**Files:**
- Modify: `frontend/src/features/agent/AgentsPage.tsx`

- [ ] **Step 1: 更新 `usableModels`**

```typescript
const usableModels = useMemo(() => {
  const rows = modelsQuery.data ?? []
  return rows.filter(
    (m: ModelProviderListItem) =>
      (Array.isArray(m.tags) ? m.tags : []).includes('CHAT') &&
      m.enabled &&
      Boolean(m.endpoint_url?.trim()) &&
      m.has_api_key,
  )
}, [modelsQuery.data])
```

- [ ] **Step 2: 手动验证**

- 无 CHAT tag 的模型不出现在下拉。  
- 去掉 CHAT 后刷新 Agent 页，已选模型回退到首个可用项（现有 effect）。

- [ ] **Step 3: Commit**

```bash
git add frontend/src/features/agent/AgentsPage.tsx
git commit -m "feat(agent): filter model picker to CHAT-tagged models"
```

---

### Task 8: Spec 回填与全量测试

**Files:**
- Modify: `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`

- [ ] **Step 1: 运行后端相关测试**

```bash
cd backend && pytest tests/test_model_provider_tags.py tests/test_agent_chat_model_factory.py tests/test_llm_model_resolver.py -v
```

Expected: 全部 PASS。

- [ ] **Step 2: 更新 spec**

- 文首 **状态** → `已实现（YYYY-MM-DD）`  
- 填满 §9 实现对照表（文件路径）  
- 增加 **实现对照（以代码为准）** 日期行

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-05-28-model-provider-tags-design.md
git commit -m "docs: backfill model-provider-tags spec implementation对照"
```

---

## 运维 / 手工验收清单

- [ ] 每个 workspace 配置字典 `MODEL_TAG`，至少含 `CHAT` 项。  
- [ ] 对已有库执行 `sql/patches/2026-05-28-sys-models-tags.sql`。  
- [ ] 创建仅 `EMBEDDING` 的模型 → Agent 不可选；直接调 Agent run API → `agent.model_tag_not_allowed`。  
- [ ] 翻译页仍仅 `model_type === 'translate'`，行为不变。

---

## Plan Self-Review

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §2 数据模型与迁移 | Task 1 |
| §3 字典 MODEL_TAG | Task 6 手工 + normalize 依赖字典 |
| §4.1–4.2 API/校验 | Task 2–3 |
| §4.3 Agent 后端 | Task 4 |
| §5 设置 UI | Task 6 |
| §6 Agent UI | Task 7 |
| §7 测试 | Task 2、4、8 |
| §8 非目标 | 未列入 Task（符合） |

- 无 TBD / “适当处理” 占位。  
- `MODEL_TAG_CHAT` / `tags` 命名全计划一致。  
- `normalize_tags` 在 Step 3 定义，Task 2 测试与其签名一致。
