# Agent 对话 CHAT tag 与专用模型列表 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 智能体对话页仅展示 Agent 可用模型（`CHAT` tag + enabled + endpoint + api_key），通过专用 `GET /agent/v2/models` 在 SQL 层过滤；跑图校验同步改为 `CHAT`。

**Architecture:** 在 `model_provider` repository 新增 `list_agent_conversation_models()`（PostgreSQL JSONB `@>` + btrim 条件 + provider/model 排序）；`agent/v2` router 暴露只读列表并映射为 `AgentConversationModelOut`（`max_tokens` 与 DB 列同名）；`ChatModelFactory` 独立校验 `MODEL_TAG_CHAT`；前端改调新 API 并移除本地过滤。不改 `/model-providers/models` 与 `app/llm` tag 规则。

**Tech Stack:** FastAPI, SQLAlchemy 2.x (JSONB), pytest, React 18, TanStack Query, TypeScript, i18next.

**Spec:** `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md`

---

## Scope Check

单个子系统：Agent 选模列表 API + `ChatModelFactory` tag 切换 + 前端 AgentsPage + `MODEL_TAG` 字典补丁。不包含规则 / 翻译 / `app/llm` / 模型供应商 CRUD 默认值变更。

---

## File Structure

### Backend

- Modify: `backend/app/sys/model_provider/domain/constants.py` — 新增 `MODEL_TAG_CHAT`
- Modify: `backend/app/sys/model_provider/infrastructure/repository.py` — `list_agent_conversation_models`
- Create: `backend/sql/patches/2026-06-01-model-tag-chat-dict-item.sql`
- Create: `backend/tests/test_model_provider_agent_models.py`
- Modify: `backend/app/agent/api/v2/schemas.py` — `AgentConversationModelOut`
- Modify: `backend/app/agent/api/v2/router.py` — `GET /models`
- Create: `backend/tests/test_agent_conversation_models_api.py`
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py` — `CHAT` 校验
- Modify: `backend/tests/test_agent_chat_model_factory.py` — TEXT → CHAT 用例

### Frontend

- Modify: `minerva-ui/src/api/agent.ts` — `listAgentConversationModels`
- Modify: `minerva-ui/src/features/agent/AgentsPage.tsx` — 新 API、移除本地过滤、`max_tokens`
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

### Docs（实现完成后）

- Modify: `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md` — 状态改为已实现

---

### Task 1: `MODEL_TAG_CHAT` 常量

**Files:**
- Modify: `backend/app/sys/model_provider/domain/constants.py`

- [ ] **Step 1: 新增常量**

```python
# backend/app/sys/model_provider/domain/constants.py
MODEL_TAG_CHAT = "CHAT"
```

放在 `MODEL_TAG_TEXT` 上一行或下一行均可；保留现有常量不变。

- [ ] **Step 2: Commit**

```bash
git add backend/app/sys/model_provider/domain/constants.py
git commit -m "feat(model): add MODEL_TAG_CHAT constant for agent conversation"
```

---

### Task 2: Repository — SQL 过滤与排序

**Files:**
- Modify: `backend/app/sys/model_provider/infrastructure/repository.py`
- Create: `backend/tests/test_model_provider_agent_models.py`

- [ ] **Step 1: 写失败测试（SQL 编译断言）**

```python
# backend/tests/test_model_provider_agent_models.py
"""Tests for agent conversation model listing query."""

from __future__ import annotations

import uuid

from sqlalchemy.dialects import postgresql

from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT
from app.sys.model_provider.infrastructure.repository import (
    agent_conversation_models_select,
)


def test_agent_conversation_models_select_filters_chat_enabled_and_secrets() -> None:
    """Compiled SQL must filter CHAT tag, enabled, endpoint, and api_key."""

    workspace_id = uuid.uuid4()
    stmt = agent_conversation_models_select(workspace_id=workspace_id)
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert MODEL_TAG_CHAT in sql
    assert "enabled" in sql.lower()
    assert "endpoint_url" in sql
    assert "api_key" in sql
    assert "provider_name" in sql
    assert "model_name" in sql


def test_agent_conversation_models_select_orders_by_provider_then_model() -> None:
    """Agent model list sorts provider_name then model_name."""

    stmt = agent_conversation_models_select(workspace_id=uuid.uuid4())
    sql = str(
        stmt.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    provider_pos = sql.lower().find("provider_name")
    model_pos = sql.lower().find("model_name")
    assert provider_pos != -1 and model_pos != -1
    assert provider_pos < model_pos
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
python -m pytest tests/test_model_provider_agent_models.py -v
```

Expected: FAIL — `agent_conversation_models_select` 未定义

- [ ] **Step 3: 实现 select 辅助函数与 repository 方法**

```python
# backend/app/sys/model_provider/infrastructure/repository.py
from sqlalchemy import func, select

from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT


def agent_conversation_models_select(*, workspace_id: uuid.UUID):
    """Build SELECT for workspace agent-usable models (caller executes)."""

    endpoint_ok = (SysModel.endpoint_url.isnot(None)) & (
        func.btrim(SysModel.endpoint_url) != ""
    )
    api_key_ok = (SysModel.api_key.isnot(None)) & (func.btrim(SysModel.api_key) != "")
    return (
        select(SysModel)
        .where(
            SysModel.workspace_id == workspace_id,
            SysModel.enabled.is_(True),
            SysModel.tags.contains([MODEL_TAG_CHAT]),
            endpoint_ok,
            api_key_ok,
        )
        .order_by(SysModel.provider_name.asc(), SysModel.model_name.asc(), SysModel.id.asc())
    )


async def list_agent_conversation_models(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> Sequence[SysModel]:
    """Return models usable for agent conversation (SQL-filtered)."""

    result = await session.execute(agent_conversation_models_select(workspace_id=workspace_id))
    return result.scalars().all()
```

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd backend
python -m pytest tests/test_model_provider_agent_models.py -v
```

Expected: PASS（2 tests）

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/model_provider/infrastructure/repository.py backend/tests/test_model_provider_agent_models.py
git commit -m "feat(model): add SQL query for agent conversation models"
```

---

### Task 3: Agent API — Schema + Router

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`
- Create: `backend/tests/test_agent_conversation_models_api.py`

- [ ] **Step 1: 新增响应 Schema**

```python
# backend/app/agent/api/v2/schemas.py
class AgentConversationModelOut(BaseModel):
    """Agent 对话页可选模型（已由服务端过滤）。"""

    id: uuid.UUID
    provider_name: str
    model_name: str
    endpoint_url: str
    max_tokens: int | None = None
    tags: list[str]
```

- [ ] **Step 2: 写失败 API 测试**

```python
# backend/tests/test_agent_conversation_models_api.py
"""Tests for GET /agent/v2/models."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.api.v2.router import router as agent_v2_router
from app.core.api.deps import require_workspace_member
from app.errors import register_exception_handlers
from app.dependencies import get_db

TEST_WORKSPACE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


async def _allow_workspace(_workspace_id: uuid.UUID) -> uuid.UUID:
    return _workspace_id


@pytest.fixture
def agent_models_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        provider_name="OpenAI",
        model_name="gpt-test",
        endpoint_url="https://example.com/v1",
        max_tokens=4096,
        tags=["CHAT", "TEXT"],
    )
    monkeypatch.setattr(
        "app.agent.api.v2.router.model_repo.list_agent_conversation_models",
        AsyncMock(return_value=[row]),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(agent_v2_router)
    app.dependency_overrides[require_workspace_member] = _allow_workspace

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_list_agent_conversation_models_maps_max_tokens(agent_models_client: TestClient) -> None:
    res = agent_models_client.get(f"/workspaces/{TEST_WORKSPACE_ID}/agent/v2/models")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["provider_name"] == "OpenAI"
    assert body[0]["model_name"] == "gpt-test"
    assert body[0]["endpoint_url"] == "https://example.com/v1"
    assert body[0]["max_tokens"] == 4096
    assert body[0]["tags"] == ["CHAT", "TEXT"]
    assert "api_key" not in body[0]
```

- [ ] **Step 3: 运行测试确认失败**

Run:

```bash
cd backend
python -m pytest tests/test_agent_conversation_models_api.py -v
```

Expected: FAIL — 404 或 route 不存在

- [ ] **Step 4: 实现 router 端点**

```python
# backend/app/agent/api/v2/router.py 顶部 import 增加
from app.agent.api.v2.schemas import AgentConversationModelOut
from app.sys.model_provider.infrastructure import repository as model_repo


def _to_agent_conversation_model(row) -> AgentConversationModelOut:
    endpoint = (row.endpoint_url or "").strip()
    return AgentConversationModelOut(
        id=row.id,
        provider_name=row.provider_name,
        model_name=row.model_name,
        endpoint_url=endpoint,
        max_tokens=row.max_tokens,
        tags=list(row.tags or []),
    )


@router.get("/models", response_model=list[AgentConversationModelOut])
async def list_agent_conversation_models(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> list[AgentConversationModelOut]:
    """返回当前工作区可用于 Agent 对话的模型（SQL 已过滤）。"""

    rows = await model_repo.list_agent_conversation_models(db, workspace_id=workspace_id)
    return [_to_agent_conversation_model(r) for r in rows]
```

- [ ] **Step 5: 运行测试确认通过**

Run:

```bash
cd backend
python -m pytest tests/test_agent_conversation_models_api.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/agent/api/v2/schemas.py backend/app/agent/api/v2/router.py backend/tests/test_agent_conversation_models_api.py
git commit -m "feat(agent): add GET /agent/v2/models for conversation model picker"
```

---

### Task 4: ChatModelFactory — TEXT → CHAT

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Modify: `backend/tests/test_agent_chat_model_factory.py`

- [ ] **Step 1: 更新失败测试**

在 `backend/tests/test_agent_chat_model_factory.py`：

- `_model_row` 默认 `tags` 改为 `["CHAT"]`
- `test_agent_chat_model_factory_rejects_missing_text_tag` 重命名为 `test_agent_chat_model_factory_rejects_missing_chat_tag`；docstring 改为 CHAT
- `test_agent_chat_model_factory_accepts_text_tag` 重命名为 `test_agent_chat_model_factory_accepts_chat_tag`；`tags=["CHAT", "EMBEDDINGS"]`
- 新增用例：仅 `TEXT` 无 `CHAT` 应拒绝

```python
def test_agent_chat_model_factory_rejects_text_without_chat_tag() -> None:
    """TEXT alone does not satisfy agent conversation tag requirement."""

    row, workspace_id = _model_row(tags=["TEXT"])

    with pytest.raises(AppError) as exc:
        ChatModelFactory.from_sys_model_row(row, workspace_id=workspace_id)

    assert exc.value.code == "agent.model_tag_not_allowed"
```

- [ ] **Step 2: 运行测试确认失败**

Run:

```bash
cd backend
python -m pytest tests/test_agent_chat_model_factory.py -v
```

Expected: FAIL — TEXT-only row 仍被接受，或 CHAT row 被拒绝

- [ ] **Step 3: 修改 factory**

```python
# backend/app/agent/infrastructure/chat_model_factory.py
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT

def _tags_allow_agent(tags: object) -> bool:
    """Return whether the model row is tagged for agent conversation usage."""

    if not isinstance(tags, list):
        return False
    return MODEL_TAG_CHAT in {str(t).strip() for t in tags if t is not None}
```

可选：将 `AppError` 文案改为「该模型未标记为 Agent 对话用途。」

- [ ] **Step 4: 运行测试确认通过**

Run:

```bash
cd backend
python -m pytest tests/test_agent_chat_model_factory.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/agent/infrastructure/chat_model_factory.py backend/tests/test_agent_chat_model_factory.py
git commit -m "feat(agent): require CHAT tag in ChatModelFactory"
```

---

### Task 5: SQL 字典补丁 — `CHAT` 项

**Files:**
- Create: `backend/sql/patches/2026-06-01-model-tag-chat-dict-item.sql`

- [ ] **Step 1: 编写 idempotent 补丁**

```sql
-- backend/sql/patches/2026-06-01-model-tag-chat-dict-item.sql
-- Insert MODEL_TAG / CHAT dictionary item for each workspace (no sys_models.tags migration).

INSERT INTO public.sys_dict_item (id, dict_uuid, code, name, parent_uuid, create_at, update_at, item_sort)
SELECT
  gen_random_uuid(),
  d.id,
  'CHAT',
  '对话',
  NULL,
  NOW() AT TIME ZONE 'UTC',
  NOW() AT TIME ZONE 'UTC',
  5
FROM public.sys_dict d
WHERE d.dict_code = 'MODEL_TAG'
  AND NOT EXISTS (
    SELECT 1
    FROM public.sys_dict_item i
    WHERE i.dict_uuid = d.id
      AND i.code = 'CHAT'
  );
```

`item_sort=5` 放在 `TEXT(1)` / `TRANSLATE(2)` 等之后；若环境无 `MODEL_TAG` 字典则本补丁 no-op（符合「不迁移模型 tags」）。

- [ ] **Step 2: 在目标库执行（开发环境）**

Run:

```bash
cd backend
psql "$DATABASE_URL" -f sql/patches/2026-06-01-model-tag-chat-dict-item.sql
```

Expected: `INSERT 0 N`（N 为缺少 CHAT 项的工作区数）或 `INSERT 0 0`

- [ ] **Step 3: Commit**

```bash
git add backend/sql/patches/2026-06-01-model-tag-chat-dict-item.sql
git commit -m "chore(sql): seed MODEL_TAG CHAT dictionary item per workspace"
```

---

### Task 6: 前端 API 客户端

**Files:**
- Modify: `minerva-ui/src/api/agent.ts`

- [ ] **Step 1: 新增类型与函数**

```typescript
export type AgentConversationModel = {
  id: string
  provider_name: string
  model_name: string
  endpoint_url: string
  max_tokens: number | null
  tags: string[]
}

export function listAgentConversationModels(workspaceId: string) {
  return apiJson<AgentConversationModel[]>(
    `/workspaces/${workspaceId}/agent/v2/models`,
  )
}
```

需在文件顶部确认已 `import { apiJson } from '@/api/client'`（若无则添加）。

- [ ] **Step 2: Commit**

```bash
git add minerva-ui/src/api/agent.ts
git commit -m "feat(agent-ui): add listAgentConversationModels API helper"
```

---

### Task 7: AgentsPage — 改用专用接口

**Files:**
- Modify: `minerva-ui/src/features/agent/AgentsPage.tsx`

- [ ] **Step 1: 替换 import 与 query**

删除：

```typescript
import { listModelProviders, type ModelProviderListItem } from '@/api/modelProviders'
```

改为：

```typescript
import { listAgentConversationModels, type AgentConversationModel } from '@/api/agent'
```

将：

```typescript
const modelsQuery = useQuery({
  queryKey: ['model-providers', workspaceId],
  queryFn: () => listModelProviders(workspaceId!),
  enabled: Boolean(workspaceId),
})
```

改为：

```typescript
const modelsQuery = useQuery({
  queryKey: ['agent-conversation-models', workspaceId],
  queryFn: () => listAgentConversationModels(workspaceId!),
  enabled: Boolean(workspaceId),
})
```

- [ ] **Step 2: 简化 usableModels**

```typescript
const usableModels = useMemo(
  () => modelsQuery.data ?? [],
  [modelsQuery.data],
)
```

删除原 `filter` 块（`TEXT` / `enabled` / `endpoint_url` / `has_api_key`）。

- [ ] **Step 3: run 时使用 max_tokens**

在 `onSend` / stream 逻辑中，将：

```typescript
modelRow?.max_tokens != null &&
Number.isFinite(modelRow.max_tokens)
  ? modelRow.max_tokens
  : null
```

改为：

```typescript
modelRow?.max_tokens != null && Number.isFinite(modelRow.max_tokens)
  ? modelRow.max_tokens
  : null
```

如有 `ModelProviderListItem` 类型注解，改为 `AgentConversationModel`。

- [ ] **Step 4: 本地冒烟**

Run frontend dev server，打开智能体页：

- 无 `CHAT` 模型时显示空状态
- 为某模型勾选 `CHAT` 并保存后，下拉出现该模型
- 发送消息 run 正常

- [ ] **Step 5: Commit**

```bash
git add minerva-ui/src/features/agent/AgentsPage.tsx
git commit -m "feat(agent-ui): load conversation models from dedicated agent API"
```

---

### Task 8: i18n 空状态文案

**Files:**
- Modify: `minerva-ui/src/i18n/locales/zh-CN.json`
- Modify: `minerva-ui/src/i18n/locales/en.json`

- [ ] **Step 1: 更新中文**

```json
"agents.noModelsConfiguredHintSuffix": "中为至少一条模型勾选「对话（CHAT）」标签，并配置「接入地址」与「API Key」，且启用。"
```

（保留 `agents.noModelsConfiguredHint` 中链到设置的句式不变。）

- [ ] **Step 2: 更新英文**

```json
"agents.noModelsConfiguredHintSuffix": " tag one model with CHAT, set endpoint URL and API key, and enable it."
```

并视需要微调 `agents.noModelsConfiguredHint` 为 “In ” 开头以衔接 suffix。

- [ ] **Step 3: Commit**

```bash
git add minerva-ui/src/i18n/locales/zh-CN.json minerva-ui/src/i18n/locales/en.json
git commit -m "docs(i18n): mention CHAT tag in agent empty model state"
```

---

### Task 9: 回归测试与 Spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md`

- [ ] **Step 1: 运行后端相关测试**

Run:

```bash
cd backend
python -m pytest tests/test_model_provider_agent_models.py tests/test_agent_conversation_models_api.py tests/test_agent_chat_model_factory.py tests/test_llm_model_resolver.py tests/test_llm_domain_models.py -v
```

Expected: 全部 PASS（`app/llm` 仍用 TEXT，不受影响）

- [ ] **Step 2: 更新 spec 状态**

将 `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md` 首行状态改为：

```markdown
**状态**：已实现（2026-06-01）
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md
git commit -m "docs: mark agent CHAT tag filter spec as implemented"
```

---

## Plan Self-Review

| Spec 要求 | 对应 Task |
|-----------|-----------|
| `GET /agent/v2/models` | Task 3 |
| SQL 过滤 CHAT + enabled + endpoint + api_key | Task 2 |
| 排序 provider → model | Task 2 |
| 响应 `max_tokens` | Task 3, 6, 7 |
| ChatModelFactory CHAT | Task 4 |
| 字典 CHAT 补丁 | Task 5 |
| 前端专用 API | Task 6, 7 |
| 空状态 i18n | Task 8 |
| 不改 `/model-providers/models` | 无相关 Task |
| 不迁移 sys_models.tags | Task 5 仅 dict item |

无 TBD / 占位步骤；类型名 `AgentConversationModelOut` / `AgentConversationModel` 前后一致。
