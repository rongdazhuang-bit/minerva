# 移除 model_type，全链路改用 tags Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 删除 `sys_models.model_type` 列及 UI/API 字段；全业务选模/校验改为 `tags` 包含关系；`app/agent` 与 `app/llm` 各自独立实现 tag 校验。

**Architecture:** 删列前 SQL 将存量 `model_type` 映射写入 `tags`（TEXT/TRANSLATE/EMBEDDINGS/RERANKING）；`model_provider` 仅维护 `MODEL_TAG` 字典与 CRUD；`app/llm/model_resolver` 用 `allowed_tags`/`excluded_tags`；`app/agent/ChatModelFactory` 本地校验 `TEXT` tag；二者互不 import。

**Tech Stack:** FastAPI, SQLAlchemy 2.x (JSONB), pytest, React 18, Ant Design, TypeScript, i18next.

**Spec:** `docs/superpowers/specs/2026-05-29-model-type-to-tags-design.md`

**前置说明:** 仓库中可能已有 2026-05-28 tags 半成品（`CHAT` tag、`model_type` 仍在）。本计划以 spec 为准完成迁移并统一 tag code。

---

## Scope Check

单个子系统演进：`sys_models` 数据模型 + model_provider CRUD + agent/llm/translate/rule 选模 + 三处前端页面。一次交付可独立验收。

---

## File Structure

### Backend — Create

| 文件 | 职责 |
|------|------|
| `backend/sql/patches/2026-05-29-drop-sys-models-model-type.sql` | 存量映射 + 删 `model_type` 列 |

### Backend — Modify

| 文件 | 职责 |
|------|------|
| `backend/app/sys/model_provider/domain/constants.py` | TEXT/TRANSLATE/EMBEDDINGS/RERANKING 常量 |
| `backend/app/sys/model_provider/domain/db/models.py` | 移除 `model_type`；tags 默认 `["TEXT"]` |
| `backend/app/sys/model_provider/service/model_provider_service.py` | 移除 MODEL_TYPE 校验与写入 |
| `backend/app/sys/model_provider/api/schemas.py` | 移除 `model_type` 字段 |
| `backend/app/sys/model_provider/api/router.py` | 移除 `model_type` 映射 |
| `backend/app/llm/domain/resolved_model.py` | `CHAT_MODEL_TAGS` 等；移除 `ResolvedModel.model_type` |
| `backend/app/llm/domain/__init__.py` | 导出新常量名 |
| `backend/app/llm/service/model_resolver.py` | `allowed_tags` / `excluded_tags` + `_tags_match` |
| `backend/app/llm/service/llm_service.py` | 参数改名 + rule excluded_tags 透传 |
| `backend/app/llm/api/router.py` | `CHAT_MODEL_TAGS` |
| `backend/app/agent/infrastructure/chat_model_factory.py` | `CHAT` → `TEXT` |
| `backend/app/translate/service/translate_llm.py` | MODEL_TAG 字典 + `TRANSLATE` tags |
| `backend/app/rule/service/rule_base_service.py` | `allowed_tags` + `excluded_tags` |
| `backend/sql/schema_postgresql.sql` | 删 `model_type` 列定义 |
| `backend/tests/test_model_provider_tags.py` | TEXT/EMBEDDINGS code |
| `backend/tests/test_agent_chat_model_factory.py` | TEXT tag |
| `backend/tests/test_llm_model_resolver.py` | tags 校验 + 新错误码 |
| `backend/tests/test_llm_domain_models.py` | 新常量断言 |
| `backend/tests/test_llm_service.py` | allowed_tags |
| `backend/tests/test_llm_strategy_unification.py` | 移除 ResolvedModel.model_type |
| `backend/tests/test_llm_multi_capability.py` | tags 替代 model_type |

### Frontend — Modify

| 文件 | 职责 |
|------|------|
| `minerva-ui/src/api/modelProviders.ts` | 移除 `model_type` |
| `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx` | 删 model_type UI/字典；默认 TEXT |
| `minerva-ui/src/features/agent/AgentsPage.tsx` | `TEXT` 过滤 |
| `minerva-ui/src/features/translate/TranslatePage.tsx` | `TRANSLATE` 过滤 |
| `minerva-ui/src/i18n/locales/zh-CN.json` | 移除 model type i18n（保留 tags） |
| `minerva-ui/src/i18n/locales/en.json` | 同上 |

### Docs — Modify

| 文件 | 职责 |
|------|------|
| `docs/ai-api.md` | tags 校验与 `ai.model_tag_mismatch` |
| `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md` | 文首 supersede 说明 |

---

### Task 1: 常量与数据库迁移

**Files:**
- Modify: `backend/app/sys/model_provider/domain/constants.py`
- Create: `backend/sql/patches/2026-05-29-drop-sys-models-model-type.sql`
- Modify: `backend/app/sys/model_provider/domain/db/models.py`
- Modify: `backend/sql/schema_postgresql.sql`

- [ ] **Step 1: 更新 tag 常量（移除 CHAT）**

```python
# backend/app/sys/model_provider/domain/constants.py
"""Model provider tag dictionary codes and well-known tag values."""

MODEL_TAG_DICT_CODE = "MODEL_TAG"
MODEL_TAG_TEXT = "TEXT"
MODEL_TAG_TRANSLATE = "TRANSLATE"
MODEL_TAG_EMBEDDINGS = "EMBEDDINGS"
MODEL_TAG_RERANKING = "RERANKING"
```

- [ ] **Step 2: 编写 SQL 补丁**

```sql
-- backend/sql/patches/2026-05-29-drop-sys-models-model-type.sql
UPDATE public.sys_models SET tags = CASE model_type
  WHEN 'text' THEN '["TEXT"]'::jsonb
  WHEN 'translate' THEN '["TRANSLATE"]'::jsonb
  WHEN 'embedding' THEN '["EMBEDDINGS"]'::jsonb
  WHEN 'rerank' THEN '["RERANKING"]'::jsonb
  ELSE tags
END;

ALTER TABLE public.sys_models DROP COLUMN IF EXISTS model_type;
```

- [ ] **Step 3: ORM 移除 model_type，更新 tags 默认值**

在 `backend/app/sys/model_provider/domain/db/models.py`：
- 删除 `model_type: Mapped[str] = mapped_column(...)` 行。
- 将 `tags` 的 `server_default` 改为 `sa.text("'[\"TEXT\"]'::jsonb")`。

- [ ] **Step 4: 同步 schema_postgresql.sql**

- 删除 `model_type varchar(64) NOT NULL` 行及 COMMENT。
- 确认 `tags jsonb NOT NULL DEFAULT '["TEXT"]'::jsonb` 存在。

- [ ] **Step 5: 本地执行补丁（开发库）**

Run: `psql $DATABASE_URL -f backend/sql/patches/2026-05-29-drop-sys-models-model-type.sql`  
Expected: `ALTER TABLE` 成功；`\d sys_models` 无 `model_type` 列。

- [ ] **Step 6: Commit**

```bash
git add backend/app/sys/model_provider/domain/constants.py \
  backend/app/sys/model_provider/domain/db/models.py \
  backend/sql/patches/2026-05-29-drop-sys-models-model-type.sql \
  backend/sql/schema_postgresql.sql
git commit -m "refactor(db): drop sys_models.model_type after tags migration"
```

---

### Task 2: model_provider API/Service 移除 model_type

**Files:**
- Modify: `backend/app/sys/model_provider/api/schemas.py`
- Modify: `backend/app/sys/model_provider/api/router.py`
- Modify: `backend/app/sys/model_provider/service/model_provider_service.py`
- Modify: `backend/tests/test_model_provider_tags.py`

- [ ] **Step 1: 更新单测 tag code（先红后绿）**

```python
# backend/tests/test_model_provider_tags.py — 替换 CHAT/EMBEDDING 为 TEXT/EMBEDDINGS
with patch.object(
    svc, "_load_dict_code_set",
    new=AsyncMock(return_value={"TEXT", "EMBEDDINGS"}),
):
    out = await svc.normalize_tags(
        session, workspace_id=uuid.uuid4(),
        tags=["EMBEDDINGS", "TEXT", "TEXT", "  TEXT  "],
    )
assert out == ["EMBEDDINGS", "TEXT"]
```

其余用例同理：`{"CHAT"}` → `{"TEXT"}`，`["CHAT", "NOPE"]` → `["TEXT", "NOPE"]`。

- [ ] **Step 2: Run tests**

Run: `cd backend && pytest tests/test_model_provider_tags.py -v`  
Expected: PASS（constants 已改；service 仍可能有 model_type 引用，若失败继续 Step 3）

- [ ] **Step 3: schemas.py 移除所有 model_type 字段**

从 `ModelProviderCreateIn`、`ModelProviderPatchIn`、`ModelProviderListItemOut`、`ModelProviderDetailOut`、`ModelProviderGroupItemOut` 删除 `model_type: ...` 行。

- [ ] **Step 4: router.py 移除 model_type**

- `_to_list_item` / `_to_group_item` / `_to_detail`：删除 `model_type=row.model_type`。
- `_to_create_dict`：删除 `"model_type": body.model_type.strip()`。
- `_to_patch_dict` 的 strip 元组：移除 `"model_type"`。

- [ ] **Step 5: service.py 移除 MODEL_TYPE 校验**

```python
async def _validate_model_fields(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider_name: str,
    auth_type: str,
    api_key: str | None,
    auth_name: str | None,
    auth_passwd: str | None,
    strict_auth: bool,
) -> None:
    allowed_providers = await _load_dict_code_set(
        session, workspace_id=workspace_id, dict_code="MODEL_PROVIDER"
    )
    if provider_name.strip() not in allowed_providers:
        raise AppError("model_provider.provider_name_invalid", "Invalid provider_name", 422)
    _assert_auth_fields(...)
```

`create_model`：
- `_validate_model_fields` 调用去掉 `model_type=...`。
- `SysModel(...)` 构造去掉 `model_type=...`。

`update_model`：
- `_validate_model_fields` 调用去掉 `model_type=row.model_type`。

- [ ] **Step 6: Run tests**

Run: `cd backend && pytest tests/test_model_provider_tags.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/sys/model_provider/api/schemas.py \
  backend/app/sys/model_provider/api/router.py \
  backend/app/sys/model_provider/service/model_provider_service.py \
  backend/tests/test_model_provider_tags.py
git commit -m "refactor(model-provider): remove model_type from API and service"
```

---

### Task 3: app/llm — tags 校验（独立于 agent）

**Files:**
- Modify: `backend/app/llm/domain/resolved_model.py`
- Modify: `backend/app/llm/domain/__init__.py`
- Modify: `backend/app/llm/service/model_resolver.py`
- Modify: `backend/tests/test_llm_model_resolver.py`
- Modify: `backend/tests/test_llm_domain_models.py`

- [ ] **Step 1: 写失败单测 — tag 不匹配**

```python
# backend/tests/test_llm_model_resolver.py
from app.llm.domain.resolved_model import CHAT_MODEL_TAGS, ResolvedModel

def _row(**overrides) -> SysModel:
    data = dict(
        ...
        tags=["TEXT"],
        # 删除 model_type 键
    )
    ...

@pytest.mark.asyncio
async def test_resolve_model_tag_mismatch() -> None:
    row = _row(tags=["EMBEDDINGS"])
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_tags=CHAT_MODEL_TAGS,
        )
    assert exc.value.code == "ai.model_tag_mismatch"
```

同步更新 `test_resolve_model_success` 使用 `allowed_tags=CHAT_MODEL_TAGS`；删除 `test_resolve_model_type_mismatch`。

- [ ] **Step 2: Run test — 确认 FAIL**

Run: `cd backend && pytest tests/test_llm_model_resolver.py::test_resolve_model_tag_mismatch -v`  
Expected: FAIL（`allowed_tags` 或 `ai.model_tag_mismatch` 未实现）

- [ ] **Step 3: resolved_model.py**

```python
# backend/app/llm/domain/resolved_model.py
CHAT_MODEL_TAGS = frozenset({"TEXT", "TRANSLATE"})
EMBEDDING_MODEL_TAGS = frozenset({"EMBEDDINGS"})
RERANK_MODEL_TAGS = frozenset({"RERANKING"})

class ResolvedModel(BaseModel):
    model_id: UUID
    model_name: str = Field(description="Upstream model field sent to the provider.")
    endpoint_url: str = Field(description="Full provider URL; used as POST target.")
    api_key: str
```

- [ ] **Step 4: domain/__init__.py 导出新名**

```python
from app.llm.domain.resolved_model import (
    CHAT_MODEL_TAGS,
    EMBEDDING_MODEL_TAGS,
    RERANK_MODEL_TAGS,
    ResolvedModel,
)
__all__ = [
    "CHAT_MODEL_TAGS",
    "EMBEDDING_MODEL_TAGS",
    "RERANK_MODEL_TAGS",
    ...
]
```

- [ ] **Step 5: model_resolver.py**

```python
def _normalize_tag_set(tags: object) -> set[str]:
    if not isinstance(tags, list):
        return set()
    return {str(t).strip() for t in tags if t is not None and str(t).strip()}


def _tags_match(
    tags: object,
    allowed_tags: frozenset[str],
    excluded_tags: frozenset[str] | None = None,
) -> bool:
    tag_set = _normalize_tag_set(tags)
    if not tag_set & allowed_tags:
        return False
    if excluded_tags and tag_set & excluded_tags:
        return False
    return True


async def resolve_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    allowed_tags: frozenset[str],
    excluded_tags: frozenset[str] | None = None,
) -> ResolvedModel:
    ...
    if not _tags_match(getattr(row, "tags", None), allowed_tags, excluded_tags):
        raise AppError(
            "ai.model_tag_mismatch",
            "模型标签不支持当前调用。",
            422,
        )
    ...
    return ResolvedModel(
        model_id=row.id,
        model_name=row.model_name.strip(),
        endpoint_url=endpoint,
        api_key=api_key,
    )
```

- [ ] **Step 6: test_llm_domain_models.py**

```python
def test_model_tag_constants() -> None:
    assert CHAT_MODEL_TAGS == frozenset({"TEXT", "TRANSLATE"})
    assert EMBEDDING_MODEL_TAGS == frozenset({"EMBEDDINGS"})
    assert RERANK_MODEL_TAGS == frozenset({"RERANKING"})

def test_resolved_model_fields() -> None:
    row = ResolvedModel(
        model_id=uuid.uuid4(),
        model_name="m",
        endpoint_url="https://x/v1/chat/completions",
        api_key="k",
    )
    assert row.model_name == "m"
```

- [ ] **Step 7: Run resolver tests**

Run: `cd backend && pytest tests/test_llm_model_resolver.py tests/test_llm_domain_models.py -v`  
Expected: PASS

- [ ] **Step 8: 新增 excluded_tags 单测**

```python
@pytest.mark.asyncio
async def test_resolve_model_excluded_tag() -> None:
    row = _row(tags=["TEXT", "TRANSLATE"])
    session = _FakeSession(row)
    with pytest.raises(AppError) as exc:
        await resolve_model(
            session,
            workspace_id=row.workspace_id,
            model_id=row.id,
            allowed_tags=frozenset({"TEXT"}),
            excluded_tags=frozenset({"TRANSLATE"}),
        )
    assert exc.value.code == "ai.model_tag_mismatch"
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/llm/domain/resolved_model.py \
  backend/app/llm/domain/__init__.py \
  backend/app/llm/service/model_resolver.py \
  backend/tests/test_llm_model_resolver.py \
  backend/tests/test_llm_domain_models.py
git commit -m "refactor(llm): resolve models by tags instead of model_type"
```

---

### Task 4: llm_service / router / translate / rule 调用方

**Files:**
- Modify: `backend/app/llm/service/llm_service.py`
- Modify: `backend/app/llm/api/router.py`
- Modify: `backend/app/translate/service/translate_llm.py`
- Modify: `backend/app/rule/service/rule_base_service.py`
- Modify: `backend/tests/test_llm_service.py`
- Modify: `backend/tests/test_llm_multi_capability.py`
- Modify: `backend/tests/test_llm_strategy_unification.py`

- [ ] **Step 1: llm_service.py — 参数改名**

所有 `complete_chat` / `stream_chat` / `complete_chat_raw` 方法：
- `allowed_types: frozenset[str] = CHAT_MODEL_TYPES` → `allowed_tags: frozenset[str] = CHAT_MODEL_TAGS`
- 新增可选 `excluded_tags: frozenset[str] | None = None`（仅 complete_chat 系列需要）
- `resolve_model(..., allowed_tags=allowed_tags, excluded_tags=excluded_tags)`
- `create_embeddings` / `rerank` 使用 `EMBEDDING_MODEL_TAGS` / `RERANK_MODEL_TAGS`

- [ ] **Step 2: llm/api/router.py**

```python
from app.llm.domain.resolved_model import CHAT_MODEL_TAGS
# allowed_types=CHAT_MODEL_TYPES → allowed_tags=CHAT_MODEL_TAGS
```

- [ ] **Step 3: translate_llm.py**

```python
from app.llm.domain.resolved_model import CHAT_MODEL_TAGS  # 仅 TRANSLATE 子集

TRANSLATE_MODEL_TAGS = frozenset({"TRANSLATE"})

async def _assert_translate_dict(session, *, workspace_id):
    allowed = await dict_service.list_items_by_dict_code(
        session, workspace_id=workspace_id, dict_code="MODEL_TAG"
    )
    codes = {i.code.strip() for i in allowed if (i.code or "").strip()}
    if "TRANSLATE" not in codes:
        raise AppError(
            "translate.model_tag_dict_missing",
            "字典 MODEL_TAG 缺少 TRANSLATE 项。",
            422,
        )

# resolve_model / complete_chat: allowed_tags=TRANSLATE_MODEL_TAGS
```

- [ ] **Step 4: rule_base_service.py**

```python
result = await llm_service.complete_chat(
    ...
    allowed_tags=frozenset({"TEXT"}),
    excluded_tags=frozenset({"TRANSLATE"}),
)
```

- [ ] **Step 5: 更新 test_llm_service.py fake_resolve**

```python
async def fake_resolve(session, *, workspace_id, model_id, allowed_tags, excluded_tags=None):
    assert allowed_tags == CHAT_MODEL_TAGS
    return resolved
```

- [ ] **Step 6: test_llm_multi_capability.py / test_llm_strategy_unification.py**

- `_row` / `ResolvedModel(...)` 去掉 `model_type`。
- `SysModel` 测试实例用 `tags=["EMBEDDINGS"]` 或 `tags=["RERANKING"]`。

- [ ] **Step 7: Run llm tests**

Run: `cd backend && pytest tests/test_llm_service.py tests/test_llm_multi_capability.py tests/test_llm_strategy_unification.py -v`  
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/llm/service/llm_service.py \
  backend/app/llm/api/router.py \
  backend/app/translate/service/translate_llm.py \
  backend/app/rule/service/rule_base_service.py \
  backend/tests/test_llm_service.py \
  backend/tests/test_llm_multi_capability.py \
  backend/tests/test_llm_strategy_unification.py
git commit -m "refactor(llm): wire allowed_tags through service and callers"
```

---

### Task 5: app/agent — TEXT tag（独立于 llm）

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/tests/test_agent_chat_model_factory.py`

- [ ] **Step 1: 更新失败单测**

```python
# test_agent_chat_model_factory.py
values = {..., "tags": ["TEXT"]}

def test_agent_chat_model_factory_rejects_missing_text_tag():
    row, workspace_id = _model_row(tags=["EMBEDDINGS"])
    ...
```

重命名 `test_agent_chat_model_factory_rejects_missing_chat_tag` → `..._missing_text_tag`；  
`test_agent_chat_model_factory_accepts_chat_tag` 使用 `tags=["TEXT", "EMBEDDINGS"]`。

- [ ] **Step 2: chat_model_factory.py**

```python
from app.sys.model_provider.domain.constants import MODEL_TAG_TEXT

def _tags_allow_agent(tags: object) -> bool:
    if not isinstance(tags, list):
        return False
    return MODEL_TAG_TEXT in {str(t).strip() for t in tags if t is not None}

# from_sys_model_row 内:
if not _tags_allow_agent(getattr(row, "tags", None)):
    raise AppError("agent.model_tag_not_allowed", "该模型未标记为文本对话用途。", 422)
```

确认文件**无** `from app.llm.service.model_resolver import ...`。

- [ ] **Step 3: Run agent tests**

Run: `cd backend && pytest tests/test_agent_chat_model_factory.py -v`  
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/agent/infrastructure/chat_model_factory.py \
  backend/tests/test_agent_chat_model_factory.py
git commit -m "refactor(agent): validate TEXT tag instead of CHAT"
```

---

### Task 6: 前端 — 移除 model_type，统一 tags 过滤

**Files:**
- Modify: `minerva-ui/src/api/modelProviders.ts`
- Modify: `minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx`
- Modify: `minerva-ui/src/features/agent/AgentsPage.tsx`
- Modify: `minerva-ui/src/features/translate/TranslatePage.tsx`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

- [ ] **Step 1: modelProviders.ts**

从 `ModelProviderListItem`、`ModelProviderDetail`、`ModelProviderCreateBody`、`ModelProviderPatchBody` 删除 `model_type: string`。

- [ ] **Step 2: ModelProvidersPage.tsx**

删除：
- `DICT_CODE_MODEL_TYPE`、`typeItems`、`modelTypeOptions`、`resolveModelTypeLabel`、`resolveModelTypeForForm`
- `FormValues.model_type`、表格 `model_type` 列、表单 `model_type` Form.Item、查看抽屉 model_type Descriptions.Item
- `buildBody` / `detailToFormValues` / `openCreate` 中的 `model_type` 逻辑
- patch diff 中的 `model_type` 比较

修改：
- `defaultTagsForCreate`：`CHAT` → `TEXT`
- 保留 tags 多选（已有）

- [ ] **Step 3: AgentsPage.tsx**

```typescript
(Array.isArray(m.tags) ? m.tags : []).includes('TEXT') &&
```

- [ ] **Step 4: TranslatePage.tsx**

```typescript
(Array.isArray(m.tags) ? m.tags : []).includes('TRANSLATE') &&
```

- [ ] **Step 5: i18n — 移除 model type 键（可选保留 col 若别处引用）**

删除 `settings.modelProvidersFieldModelType*`、`settings.modelProvidersColModelType`（若存在）等仅用于 model_type 的键。

- [ ] **Step 6: Typecheck**

Run: `cd minerva-ui && npm run build`  
Expected: 编译成功，无 `model_type` 类型错误。

- [ ] **Step 7: Commit**

```bash
git add minerva-ui/src/api/modelProviders.ts \
  minerva-ui/src/features/settings/model-providers/ModelProvidersPage.tsx \
  minerva-ui/src/features/agent/AgentsPage.tsx \
  minerva-ui/src/features/translate/TranslatePage.tsx \
  minerva-ui/src/i18n/locales/zh-CN.json \
  minerva-ui/src/i18n/locales/en.json
git commit -m "refactor(ui): drop model_type field, filter models by tags"
```

---

### Task 7: 文档与全量回归

**Files:**
- Modify: `docs/ai-api.md`
- Modify: `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`
- Modify: `docs/superpowers/specs/2026-05-29-model-type-to-tags-design.md`（状态 → 已实现）

- [ ] **Step 1: 更新 docs/ai-api.md**

- `model_resolver` 描述改为校验 `tags`（`allowed_tags` / `excluded_tags`）。
- 端点映射：`TEXT|TRANSLATE` / `EMBEDDINGS` / `RERANKING`。
- 错误码表：`ai.model_type_mismatch` → `ai.model_tag_mismatch`。

- [ ] **Step 2: 旧 spec 文首加 supersede 说明**

```markdown
> **Superseded（2026-05-29）:** 「保留 model_type」条款已由 `2026-05-29-model-type-to-tags-design.md` 替代。
```

- [ ] **Step 3: 全量后端测试**

Run: `cd backend && pytest tests/test_model_provider_tags.py tests/test_agent_chat_model_factory.py tests/test_llm_model_resolver.py tests/test_llm_domain_models.py tests/test_llm_service.py tests/test_llm_multi_capability.py tests/test_llm_strategy_unification.py -v`  
Expected: 全部 PASS

- [ ] **Step 4: grep 确认无残留 model_type 业务引用**

Run: `rg "model_type|CHAT_MODEL_TYPES|MODEL_TAG_CHAT|allowed_types" backend/app --glob '!**/__pycache__/**'`  
Expected: 无命中（测试文件除外或已更新）

- [ ] **Step 5: Commit**

```bash
git add docs/ai-api.md docs/superpowers/specs/
git commit -m "docs: update AI API and specs for tags-only model selection"
```

---

## Spec Coverage Checklist

| Spec § | Task |
|--------|------|
| 删 DB model_type + 映射 | Task 1 |
| model_provider 无 model_type | Task 2 |
| agent TEXT 独立校验 | Task 5 |
| llm allowed/excluded tags | Task 3, 4 |
| translate TRANSLATE | Task 4 |
| rule TEXT 不含 TRANSLATE | Task 4 |
| 前端三页 + API 类型 | Task 6 |
| 文档 | Task 7 |
| agent/llm 不互相 import | Task 3, 5（各自文件内确认） |

## Manual Acceptance

1. 工作区 `MODEL_TAG` 字典含 TEXT、TRANSLATE、EMBEDDINGS、RERANKING。
2. 设置 → 模型供应商：无「模型类型」；tags 多选保存正常。
3. Agent 下拉仅 TEXT 模型；EMBEDDINGS-only 模型不可选。
4. 翻译页仅 TRANSLATE 模型。
5. 直接调 Agent API 用无 TEXT tag 的 model_id → 422 `agent.model_tag_not_allowed`。
6. POST `/chat/completions` 用 EMBEDDINGS-only model → 422 `ai.model_tag_mismatch`。

---

## Plan Self-Review

- [x] 无 TBD/TODO 占位步骤。
- [x] 每 Task 含具体文件路径与代码片段。
- [x] 常量名前后一致：`CHAT_MODEL_TAGS`、`allowed_tags`、`MODEL_TAG_TEXT`。
- [x] 覆盖 spec 全部模块与非目标边界。
- [x] 考虑 2026-05-28 半成品（CHAT → TEXT 迁移）作为前置说明。
