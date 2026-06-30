# Agent 多模态图片上传 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Agent 对话中 `MULTIMODAL` 标签模型支持图片上传与 vision 解析；图片经工作区 S3/Local 存储，平时以 URL 流转，仅在 LLM 调用边界转 base64；Planner / SubAgent / Synthesizer 全链路可见附件。

**Architecture:** 新增 `WorkspaceFileService`（`resolve_active_storage` 门面）与 `vision_messages.py`（Run 级 base64 缓存）；扩展 Agent v2 upload/run/config API；`GraphDeps` 携带 `user_attachments` 与 `VisionAttachmentCache`；前端 composer 按 `supports_vision` 门控上传。不改 `app/llm` 与其它模块选模规则。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, LangChain HumanMessage content parts, pytest, React 18 + Ant Design Upload, TanStack Query, TypeScript, i18next.

**Spec:** `docs/superpowers/specs/2026-06-30-agent-vision-image-upload-design.md`

---

## Scope Check

单个子系统：Agent 多模态附件 + 工作区文件门面 + `MODEL_TAG_MULTIMODAL` 选模扩展。不包含 dataset OCR、规则、`app/llm` HTTP 变更。

---

## File Structure

### Backend — 新建

| 路径 | 职责 |
|------|------|
| `backend/app/files/__init__.py` | 包导出 |
| `backend/app/files/domain/models.py` | `WorkspaceFileUploadResult` |
| `backend/app/files/service/workspace_file_service.py` | S3/Local 统一 upload/read/url |
| `backend/app/agent/infrastructure/vision_messages.py` | MIME 归一化、`VisionAttachmentCache`、`build_vision_human_message` |
| `backend/app/agent/service/agent_attachment_service.py` | 上传校验、run 附件校验、持久化 meta 组装 |
| `backend/sql/patches/2026-06-30-model-tag-multimodal-dict-item.sql` | `MODEL_TAG` / `MULTIMODAL` 字典项 |
| `backend/tests/test_vision_messages.py` | VisionMessageBuilder 单元测试 |
| `backend/tests/test_workspace_file_service.py` | 门面分支单元测试（mock S3/Local） |
| `backend/tests/test_agent_vision_api.py` | upload + run 422 集成测试 |

### Backend — 修改

| 路径 | 职责 |
|------|------|
| `backend/app/sys/model_provider/domain/constants.py` | `MODEL_TAG_MULTIMODAL` |
| `backend/app/sys/model_provider/infrastructure/repository.py` | `CHAT` OR `MULTIMODAL` 过滤 |
| `backend/app/agent/infrastructure/chat_model_factory.py` | tag 扩展 + vision 校验 helper |
| `backend/app/config.py` | 三个 `AGENT_VISION_*` 字段 |
| `backend/.env.example` | 文档注释 |
| `backend/app/agent/api/v2/schemas.py` | Attachment / config / message schemas |
| `backend/app/agent/api/v2/router.py` | upload、config、message 映射 |
| `backend/app/agent/service/agent_graph_run_service.py` | attachments 注入、持久化 meta |
| `backend/app/agent/graphs/state.py` | `user_attachments` |
| `backend/app/agent/graphs/deps.py` | cache、attachments、supports_vision |
| `backend/app/agent/graphs/nodes/planner.py` | vision HumanMessage |
| `backend/app/agent/graphs/nodes/synthesizer.py` | vision HumanMessage |
| `backend/app/agent/graphs/nodes/subagent_runner.py` | vision user input |
| `backend/app/agent/infrastructure/chat_history.py` | 异步 history 重建 |

### Frontend — 修改

| 路径 | 职责 |
|------|------|
| `frontend/src/api/agent.ts` | 类型 + upload + config |
| `frontend/src/features/agent/AgentsPage.tsx` | 上传 UI、消息缩略图 |
| `frontend/src/features/agent/AgentsPage.css` | 附件预览样式 |
| `frontend/src/i18n/locales/zh-CN.json` | 文案 |
| `frontend/src/i18n/locales/en.json` | 文案 |

### Docs（实现完成后）

| 路径 | 职责 |
|------|------|
| `docs/superpowers/specs/2026-06-30-agent-vision-image-upload-design.md` | 状态 → 已实现 |

---

### Task 1: `MODEL_TAG_MULTIMODAL` 与字典补丁

**Files:**
- Modify: `backend/app/sys/model_provider/domain/constants.py`
- Create: `backend/sql/patches/2026-06-30-model-tag-multimodal-dict-item.sql`

- [ ] **Step 1: 新增常量**

```python
# backend/app/sys/model_provider/domain/constants.py
MODEL_TAG_MULTIMODAL = "MULTIMODAL"
```

- [ ] **Step 2: SQL 补丁（idempotent）**

```sql
-- backend/sql/patches/2026-06-30-model-tag-multimodal-dict-item.sql
INSERT INTO public.sys_dict_item (id, dict_uuid, code, name, parent_uuid, create_at, update_at, item_sort)
SELECT
  gen_random_uuid(),
  d.id,
  'MULTIMODAL',
  '多模态',
  NULL,
  NOW() AT TIME ZONE 'UTC',
  NOW() AT TIME ZONE 'UTC',
  6
FROM public.sys_dict d
WHERE d.dict_code = 'MODEL_TAG'
  AND NOT EXISTS (
    SELECT 1 FROM public.sys_dict_item i
    WHERE i.dict_uuid = d.id AND i.code = 'MULTIMODAL'
  );
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/sys/model_provider/domain/constants.py backend/sql/patches/2026-06-30-model-tag-multimodal-dict-item.sql
git commit -m "feat(model): add MODEL_TAG_MULTIMODAL dictionary constant and seed patch"
```

---

### Task 2: Agent 选模 SQL — `CHAT` OR `MULTIMODAL`

**Files:**
- Modify: `backend/app/sys/model_provider/infrastructure/repository.py`
- Create: `backend/tests/test_model_provider_agent_models_multimodal.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_model_provider_agent_models_multimodal.py
from sqlalchemy.dialects import postgresql
from app.sys.model_provider.infrastructure.repository import agent_conversation_models_select
import uuid

def test_agent_models_select_includes_chat_or_multimodal():
    stmt = agent_conversation_models_select(workspace_id=uuid.uuid4())
    sql = str(stmt.compile(dialect=postgresql.dialect()))
    assert "MULTIMODAL" in sql or "multimodal" in sql.lower()
    assert "CHAT" in sql
```

- [ ] **Step 2: 运行测试确认 FAIL**

Run: `cd backend && python -m pytest tests/test_model_provider_agent_models_multimodal.py -v`  
Expected: FAIL（SQL 尚未包含 MULTIMODAL OR 条件）

- [ ] **Step 3: 修改 repository**

```python
# backend/app/sys/model_provider/infrastructure/repository.py
from sqlalchemy import func, or_, select
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT, MODEL_TAG_MULTIMODAL

def agent_conversation_models_select(*, workspace_id: uuid.UUID):
    endpoint_ok = (SysModel.endpoint_url.isnot(None)) & (func.btrim(SysModel.endpoint_url) != "")
    api_key_ok = (SysModel.api_key.isnot(None)) & (func.btrim(SysModel.api_key) != "")
    tag_ok = or_(
        SysModel.tags.contains([MODEL_TAG_CHAT]),
        SysModel.tags.contains([MODEL_TAG_MULTIMODAL]),
    )
    return (
        select(SysModel)
        .where(
            SysModel.workspace_id == workspace_id,
            SysModel.enabled.is_(True),
            tag_ok,
            endpoint_ok,
            api_key_ok,
        )
        .order_by(
            SysModel.provider_name.asc(),
            SysModel.model_name.asc(),
            SysModel.id.asc(),
        )
    )
```

- [ ] **Step 4: 运行测试 PASS**

Run: `cd backend && python -m pytest tests/test_model_provider_agent_models_multimodal.py -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/sys/model_provider/infrastructure/repository.py backend/tests/test_model_provider_agent_models_multimodal.py
git commit -m "feat(agent): allow CHAT or MULTIMODAL models in conversation list"
```

---

### Task 3: `ChatModelFactory` tag 扩展

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_model_factory.py`
- Create: `backend/tests/test_agent_chat_model_factory_tags.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_agent_chat_model_factory_tags.py
import uuid
import pytest
from app.agent.infrastructure.chat_model_factory import (
    _tags_allow_agent,
    model_supports_vision,
)
from app.exceptions import AppError
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT, MODEL_TAG_MULTIMODAL

def test_tags_allow_agent_multimodal_only():
    assert _tags_allow_agent([MODEL_TAG_MULTIMODAL]) is True

def test_model_supports_vision():
    assert model_supports_vision([MODEL_TAG_MULTIMODAL]) is True
    assert model_supports_vision([MODEL_TAG_CHAT]) is False
```

- [ ] **Step 2: 实现**

```python
# chat_model_factory.py 内新增
from app.sys.model_provider.domain.constants import MODEL_TAG_CHAT, MODEL_TAG_MULTIMODAL

def _normalize_tags(tags: object) -> set[str]:
    if not isinstance(tags, list):
        return set()
    return {str(t).strip() for t in tags if t is not None}

def _tags_allow_agent(tags: object) -> bool:
    normalized = _normalize_tags(tags)
    return MODEL_TAG_CHAT in normalized or MODEL_TAG_MULTIMODAL in normalized

def model_supports_vision(tags: object) -> bool:
    return MODEL_TAG_MULTIMODAL in _normalize_tags(tags)

def assert_model_supports_vision(row: SysModel) -> None:
    if not model_supports_vision(getattr(row, "tags", None)):
        raise AppError(
            "agent.model_vision_not_supported",
            "该模型不支持图片输入，请选择多模态模型。",
            422,
        )
```

将 `from_sys_model_row` 内 `_tags_allow_agent` 调用保持不变（已覆盖 MULTIMODAL）。

- [ ] **Step 3: pytest PASS + Commit**

```bash
cd backend && python -m pytest tests/test_agent_chat_model_factory_tags.py -v
git add backend/app/agent/infrastructure/chat_model_factory.py backend/tests/test_agent_chat_model_factory_tags.py
git commit -m "feat(agent): accept MULTIMODAL tag in ChatModelFactory"
```

---

### Task 4: Settings 与 MIME 工具

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Create: `backend/app/agent/infrastructure/vision_mime.py`（或并入 `vision_messages.py` 顶部）

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_vision_mime.py
from app.agent.infrastructure.vision_mime import normalize_vision_mime, allowed_vision_mime_set

def test_normalize_jpg_alias():
    assert normalize_vision_mime("image/jpg") == "image/jpeg"

def test_allowed_set_includes_png():
    allowed = allowed_vision_mime_set("image/jpeg,image/jpg,image/png")
    assert "image/jpeg" in allowed
    assert "image/png" in allowed
```

- [ ] **Step 2: 实现 vision_mime.py**

```python
# backend/app/agent/infrastructure/vision_mime.py
from __future__ import annotations

ALLOWED_VISION_EXTENSIONS = frozenset({".jpg", ".jpeg", ".png"})

def normalize_vision_mime(raw: str | None) -> str | None:
    if raw is None:
        return None
    value = raw.strip().lower()
    if value == "image/jpg":
        return "image/jpeg"
    return value or None

def allowed_vision_mime_set(config_value: str) -> frozenset[str]:
    parts = [normalize_vision_mime(p) for p in config_value.split(",")]
    return frozenset(p for p in parts if p)
```

- [ ] **Step 3: config.py 新增字段**

```python
agent_vision_image_max_count: int = Field(
    default=1,
    ge=1,
    le=20,
    validation_alias=AliasChoices("AGENT_VISION_IMAGE_MAX_COUNT", "agent_vision_image_max_count"),
)
agent_vision_image_max_bytes: int = Field(
    default=5_242_880,
    ge=1,
    validation_alias=AliasChoices("AGENT_VISION_IMAGE_MAX_BYTES", "agent_vision_image_max_bytes"),
)
agent_vision_image_allowed_mime: str = Field(
    default="image/jpeg,image/jpg,image/png",
    validation_alias=AliasChoices("AGENT_VISION_IMAGE_ALLOWED_MIME", "agent_vision_image_allowed_mime"),
)
```

`.env.example` 增加三行注释示例。

- [ ] **Step 4: pytest PASS + Commit**

---

### Task 5: `WorkspaceFileService`

**Files:**
- Create: `backend/app/files/domain/models.py`
- Create: `backend/app/files/service/workspace_file_service.py`
- Create: `backend/tests/test_workspace_file_service.py`

- [ ] **Step 1: 写失败测试（mock active storage）**

```python
# backend/tests/test_workspace_file_service.py
import uuid
from unittest.mock import AsyncMock, MagicMock
import pytest
from app.files.service.workspace_file_service import WorkspaceFileService
from app.sys.file_storage.service.storage_resolver import ActiveStorage

@pytest.mark.asyncio
# type: ignore
async def test_read_object_bytes_local(monkeypatch):
    workspace_id = uuid.uuid4()
    session = AsyncMock()
    service = WorkspaceFileService(session=session)
    active = ActiveStorage(kind="DEFAULT_LOCAL", storage_id=None, local_path=None)
    fake_gateway = MagicMock()
    fake_gateway.get_object_bytes.return_value = b"\x89PNG"
    monkeypatch.setattr(
        service,
        "_resolve_local_gateway",
        AsyncMock(return_value=(active, fake_gateway)),
    )
    monkeypatch.setattr(
        "app.files.service.workspace_file_service.resolve_active_storage",
        AsyncMock(return_value=active),
    )
    data = await service.read_object_bytes(
        workspace_id=workspace_id,
        object_key="agent_vision/2026/06/x.png",
    )
    assert data == b"\x89PNG"
```

- [ ] **Step 2: 实现 WorkspaceFileService**

核心逻辑：

```python
async def upload_file(...) -> WorkspaceFileUploadResult:
    active = await resolve_active_storage(self._session, workspace_id=workspace_id)
    if active.kind == "S3":
        result = await self._s3.upload_file(...)
    else:
        result = await self._local.upload_file(...)
    return WorkspaceFileUploadResult(
        object_key=result.object_key,
        file_name=result.file_name,
        content_type=result.content_type,
        size=result.size,
        download_url=result.download_url,
    )

async def read_object_bytes(self, *, workspace_id, object_key) -> bytes:
    active = await resolve_active_storage(self._session, workspace_id=workspace_id)
    if active.kind == "S3":
        proxy = await self._s3.get_download_proxy(workspace_id=workspace_id, object_key=object_key)
        try:
            return proxy.stream.read()
        finally:
            proxy.stream.close()
    else:
        _, gateway = await self._resolve_local_gateway(workspace_id=workspace_id)
        return gateway.get_object_bytes(object_key=object_key)
```

构造函数内 lazy 构建 `S3FileService(session)` 与 `LocalFileService(session)`。

- [ ] **Step 3: pytest PASS + Commit**

---

### Task 6: `VisionMessageBuilder`

**Files:**
- Create: `backend/app/agent/infrastructure/vision_messages.py`
- Create: `backend/tests/test_vision_messages.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_vision_messages.py
import base64
import uuid
from unittest.mock import AsyncMock
import pytest
from langchain_core.messages import HumanMessage
from app.agent.infrastructure.vision_messages import (
    VisionAttachmentCache,
    build_vision_human_message,
)

@pytest.mark.asyncio
async def test_build_vision_human_message_with_attachment():
    workspace_id = uuid.uuid4()
    png = b"\x89PNG\r\n\x1a\n"
    file_service = AsyncMock()
    file_service.read_object_bytes = AsyncMock(return_value=png)
    cache = VisionAttachmentCache()
    msg = await build_vision_human_message(
        "描述图片",
        attachments=[{
            "object_key": "agent_vision/2026/06/a.png",
            "content_type": "image/png",
        }],
        workspace_id=workspace_id,
        file_service=file_service,
        cache=cache,
    )
    assert isinstance(msg, HumanMessage)
    assert isinstance(msg.content, list)
    assert msg.content[0]["type"] == "text"
    assert msg.content[1]["type"] == "image_url"
    assert msg.content[1]["image_url"]["url"].startswith("data:image/png;base64,")
    # 第二次命中 cache
    await build_vision_human_message(
        "again",
        attachments=[{"object_key": "agent_vision/2026/06/a.png", "content_type": "image/png"}],
        workspace_id=workspace_id,
        file_service=file_service,
        cache=cache,
    )
    assert file_service.read_object_bytes.await_count == 1

@pytest.mark.asyncio
async def test_build_vision_human_message_text_only():
    msg = await build_vision_human_message(
        "hello",
        attachments=[],
        workspace_id=uuid.uuid4(),
        file_service=AsyncMock(),
        cache=VisionAttachmentCache(),
    )
    assert msg.content == "hello"
```

- [ ] **Step 2: 实现 vision_messages.py**

```python
import base64
import uuid
from dataclasses import dataclass, field
from langchain_core.messages import HumanMessage
from app.files.service.workspace_file_service import WorkspaceFileService
from app.agent.infrastructure.vision_mime import normalize_vision_mime

@dataclass
class VisionAttachmentCache:
    _data_urls: dict[str, str] = field(default_factory=dict)

    def get(self, object_key: str) -> str | None:
        return self._data_urls.get(object_key)

    def put(self, object_key: str, data_url: str) -> None:
        self._data_urls[object_key] = data_url

async def build_vision_human_message(
    text: str,
    attachments: list[dict],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
    include_images: bool = True,
) -> HumanMessage:
    body = (text or "").strip()
    if not attachments or not include_images:
        return HumanMessage(content=body)
    parts: list[dict] = []
    if body:
        parts.append({"type": "text", "text": body})
    for att in attachments:
        key = str(att.get("object_key") or "").strip()
        if not key:
            continue
        cached = cache.get(key)
        if cached is None:
            raw = await file_service.read_object_bytes(workspace_id=workspace_id, object_key=key)
            mime = normalize_vision_mime(att.get("content_type")) or "application/octet-stream"
            b64 = base64.b64encode(raw).decode("ascii")
            cached = f"data:{mime};base64,{b64}"
            cache.put(key, cached)
        parts.append({"type": "image_url", "image_url": {"url": cached}})
    if not parts:
        return HumanMessage(content=body)
    if len(parts) == 1 and parts[0]["type"] == "text":
        return HumanMessage(content=body)
    return HumanMessage(content=parts)
```

- [ ] **Step 3: pytest PASS + Commit**

---

### Task 7: `agent_attachment_service` 与 Upload API

**Files:**
- Create: `backend/app/agent/service/agent_attachment_service.py`
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`

- [ ] **Step 1: schemas**

```python
class AgentAttachmentUploadOut(BaseModel):
    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str

class AgentV2ConfigOut(BaseModel):
    memory_backend: str
    vision_image_max_count: int
    vision_image_max_bytes: int
    vision_image_allowed_mime: list[str]

class AgentConversationModelOut(BaseModel):
    # 现有字段 ...
    supports_vision: bool = False
```

- [ ] **Step 2: agent_attachment_service 校验函数**

```python
AGENT_VISION_MODULE_PREFIX = "agent_vision"

def assert_agent_vision_object_key(object_key: str) -> str:
    key = object_key.strip()
    if not key.startswith(f"{AGENT_VISION_MODULE_PREFIX}/"):
        raise AppError("agent.vision_attachment_invalid", "Invalid attachment object_key", 422)
    return key

async def validate_upload_file(*, payload: bytes, filename: str, content_type: str | None) -> str:
    # 扩展名 + MIME + size；返回归一化 MIME
    ...

async def resolve_attachment_meta_for_run(session, *, workspace_id, items: list[AgentAttachmentIn]) -> list[dict]:
    # 校验存在性、组装含 download_url 的 dict 列表
    ...
```

- [ ] **Step 3: router 端点**

```python
@router.post("/attachments:upload", response_model=AgentAttachmentUploadOut, status_code=201)
async def upload_agent_attachment(
    workspace_id: uuid.UUID,
    file: UploadFile | None = File(default=None),
    ...
):
    ...

@router.get("/config", response_model=AgentV2ConfigOut)
async def get_agent_v2_config(...):
    return AgentV2ConfigOut(
        memory_backend=settings.agent_memory_backend,
        vision_image_max_count=settings.agent_vision_image_max_count,
        vision_image_max_bytes=settings.agent_vision_image_max_bytes,
        vision_image_allowed_mime=sorted(
            allowed_vision_mime_set(settings.agent_vision_image_allowed_mime)
        ),
    )
```

`_to_agent_conversation_model` 增加 `supports_vision=model_supports_vision(row.tags)`。

- [ ] **Step 4: 集成测试 upload 422（无 file）**

```python
# backend/tests/test_agent_vision_api.py — 使用现有 test client fixture
async def test_upload_requires_file(client, workspace_headers):
    res = await client.post(f"/workspaces/{wid}/agent/v2/attachments:upload", headers=...)
    assert res.status_code == 422
```

- [ ] **Step 5: Commit**

---

### Task 8: Run 协议、持久化与 Graph 注入

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py` — `AgentAttachmentIn`, `AgentRunCreateV2.attachments`
- Modify: `backend/app/agent/service/agent_graph_run_service.py`
- Modify: `backend/app/agent/graphs/state.py`
- Modify: `backend/app/agent/graphs/deps.py`

- [ ] **Step 1: 扩展 AgentRunCreateV2 validator**

```python
@model_validator(mode="after")
def _require_message_or_attachment_or_skill(self) -> "AgentRunCreateV2":
    if self.user_message.strip() or self.attachments:
        return self
    # 保留 skill-only 逻辑
    ...
```

- [ ] **Step 2: run service 流程**

在 `stream_run` 入参增加 `attachments: list[AgentAttachmentIn]`：

1. 若 `attachments` 非空：`assert_model_supports_vision(sys_row)`
2. `len(attachments) > settings.agent_vision_image_max_count` → `agent.vision_attachment_limit`
3. `resolved = await resolve_attachment_meta_for_run(...)`（含 download_url）
4. `append_agent_message(..., content=user_message, meta_json={"attachments": resolved})`
5. `GraphDeps` 新增：
   - `user_attachments: list[dict]`
   - `vision_cache: VisionAttachmentCache`
   - `model_supports_vision: bool`
   - `workspace_file_service: WorkspaceFileService`（或在 deps 存 session factory）
6. 初始 state：`user_attachments=resolved`, `user_message=user_message`

- [ ] **Step 3: GraphState**

```python
user_attachments: list[dict]
```

- [ ] **Step 4: 集成测试 — 非 MULTIMODAL + attachments → 422**

- [ ] **Step 5: Commit**

---

### Task 9: 全图节点 + chat_history

**Files:**
- Modify: `backend/app/agent/graphs/nodes/planner.py`
- Modify: `backend/app/agent/graphs/nodes/subagent_runner.py`
- Modify: `backend/app/agent/graphs/nodes/synthesizer.py`
- Modify: `backend/app/agent/infrastructure/chat_history.py`

- [ ] **Step 1: 扩展 chat_history**

```python
async def build_conversation_messages_for_run(
    rows: list[AgentMessage],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
    include_vision_in_history: bool,
    max_messages: int,
) -> list[BaseMessage]:
    ...
```

对用户行：读 `meta_json.attachments`；`include_vision_in_history=False` 时仅文本。

新增：

```python
async def messages_with_user_input_vision(
    conversation_messages: list[BaseMessage],
    user_input: str,
    attachments: list[dict],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
    include_images: bool = True,
) -> list[BaseMessage]:
    prior, _ = split_trailing_user_message(conversation_messages)
    user_msg = await build_vision_human_message(
        user_input, attachments, workspace_id=workspace_id,
        file_service=file_service, cache=cache, include_images=include_images,
    )
    return [*prior, user_msg]
```

- [ ] **Step 2: planner.py**

将固定字符串 `HumanMessage(content=...)` 改为：

```python
user_msg = await build_vision_human_message(
    request_block_text,
    state.get("user_attachments") or [],
    workspace_id=deps.workspace_id,
    file_service=...,  # 从 deps 取
    cache=deps.vision_cache,
    include_images=deps.model_supports_vision,
)
planner_messages = [SystemMessage(...), user_msg]
```

- [ ] **Step 3: subagent_runner.py**

```python
inputs = {
    "messages": await messages_with_user_input_vision(
        history,
        effective_goal,
        deps.user_attachments or [],
        workspace_id=deps.workspace_id,
        file_service=deps.workspace_file_service,
        cache=deps.vision_cache,
        include_images=deps.model_supports_vision,
    )
}
```

- [ ] **Step 4: synthesizer.py**

无 results 分支与 merge 分支的用户 `HumanMessage` 均改用 `build_vision_human_message`（merge 时图片附在用户问题 part）。

- [ ] **Step 5: agent_graph_run_service 构建 conversation_messages**

跑图前：

```python
conversation_messages = await build_conversation_messages_for_run(
    msg_rows,
    workspace_id=workspace_id,
    file_service=file_service,
    cache=vision_cache,
    include_vision_in_history=model_supports_vision(sys_row.tags),
    max_messages=settings.agent_chat_history_message_limit,
)
```

- [ ] **Step 6: Commit**

---

### Task 10: 会话 API 暴露 attachments

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py` — `AgentMessageAttachmentOut`
- Modify: `backend/app/agent/api/v2/router.py` — `get_agent_session_detail` 映射

- [ ] **Step 1: schema**

```python
class AgentMessageAttachmentOut(BaseModel):
    object_key: str
    file_name: str | None = None
    content_type: str | None = None
    size: int | None = None
    download_url: str | None = None

class AgentMessageOut(BaseModel):
    ...
    attachments: list[AgentMessageAttachmentOut] = Field(default_factory=list)
```

- [ ] **Step 2: 映射 helper**

```python
def _attachments_from_meta(meta_json: dict | None) -> list[AgentMessageAttachmentOut]:
    if not isinstance(meta_json, dict):
        return []
    raw = meta_json.get("attachments")
    if not isinstance(raw, list):
        return []
    out: list[AgentMessageAttachmentOut] = []
    for item in raw:
        if isinstance(item, dict) and item.get("object_key"):
            out.append(AgentMessageAttachmentOut.model_validate(item))
    return out
```

- [ ] **Step 3: Commit**

---

### Task 11: 前端 API 与 AgentsPage

**Files:**
- Modify: `frontend/src/api/agent.ts`
- Modify: `frontend/src/features/agent/AgentsPage.tsx`
- Modify: `frontend/src/features/agent/AgentsPage.css`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: agent.ts 类型与 API**

```typescript
export type AgentAttachmentMeta = {
  object_key: string
  file_name?: string | null
  content_type?: string | null
  size?: number | null
  download_url?: string | null
}

export type AgentRunCreateBodyV2 = {
  user_message: string
  attachments?: AgentAttachmentMeta[]
  // ...
}

export type AgentV2Config = {
  memory_backend: string
  vision_image_max_count: number
  vision_image_max_bytes: number
  vision_image_allowed_mime: string[]
}

export type AgentConversationModel = {
  // ...
  supports_vision: boolean
}

export async function uploadAgentAttachment(
  workspaceId: string,
  file: File,
  onProgress?: (pct: number) => void,
): Promise<AgentAttachmentMeta> { /* multipart POST attachments:upload */ }
```

- [ ] **Step 2: AgentsPage state**

```typescript
const [pendingAttachments, setPendingAttachments] = useState<AgentAttachmentMeta[]>([])
const agentConfigQuery = useQuery({ queryKey: ['agent-v2-config', workspaceId], ... })
const selectedModelSupportsVision = useMemo(
  () => usableModels.find(m => m.id === modelId)?.supports_vision ?? false,
  [usableModels, modelId],
)
```

- [ ] **Step 3: Composer 上传**

- `supports_vision && pendingAttachments.length < config.vision_image_max_count` 时显示 `Upload` + `PictureOutlined`
- `beforeUpload`：`validate mime/size` → `uploadAgentAttachment` → push to `pendingAttachments`
- 预览区：`<img src={download_url} />` + 删除按钮
- `runAgentTurn`：body 增加 `attachments: pendingAttachments.map(({ object_key, file_name, content_type }) => ...)`
- 发送成功后 `setPendingAttachments([])`

- [ ] **Step 4: 消息气泡展示 attachments**

用户消息渲染：`content` + `attachments?.map(a => <img key={a.object_key} src={a.download_url} />)`

- [ ] **Step 5: i18n 键**

`agents.vision.upload`, `agents.vision.tooLarge`, `agents.vision.mimeNotAllowed`, `agents.vision.limitReached`

- [ ] **Step 6: 手动冒烟**

1. 模型勾选 `MULTIMODAL` → 出现上传按钮  
2. 上传 png → 预览 → 发送「描述图片」→ 模型回复  
3. 刷新会话 → 缩略图仍可见  
4. 切换仅 `CHAT` 模型 → 无上传按钮  

- [ ] **Step 7: Commit**

---

### Task 12: 文档与 spec 状态

**Files:**
- Modify: `docs/superpowers/specs/2026-06-30-agent-vision-image-upload-design.md`

- [ ] **Step 1: 将「状态」改为「已实现（YYYY-MM-DD）」并补充实现说明链接本 plan**

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-06-30-agent-vision-image-upload-design.md docs/superpowers/plans/2026-06-30-agent-vision-image-upload.md
git commit -m "docs: mark agent vision image upload spec implemented"
```

---

## Spec Coverage Checklist

| Spec 章节 | Task |
|-----------|------|
| §2 标签与选模 | Task 1–3, 7 (`supports_vision`) |
| §3 环境变量 | Task 4, 7 (config API) |
| §4 存储与上传 | Task 5, 7 |
| §5 Run 与持久化 | Task 8, 10 |
| §6 跑图全链路 | Task 6, 9 |
| §7 前端 | Task 11 |
| §8 错误码 | Task 7–8 (`AppError` codes) |
| §6.5 历史非 vision 模型 | Task 9 (`include_vision_in_history`) |

---

## Manual Test Checklist（实现后）

- [ ] S3 工作区：upload → run → 模型识别图片内容
- [ ] Local 工作区：同上
- [ ] `AGENT_VISION_IMAGE_MAX_COUNT=2`：可传 2 张；第 3 张前端阻止
- [ ] `image/jpg` 文件上传成功且 MIME 存为 `image/jpeg`
- [ ] 非 MULTIMODAL 模型 run 带 attachments → 422
- [ ] DB / SSE payload 中无 base64 字符串
