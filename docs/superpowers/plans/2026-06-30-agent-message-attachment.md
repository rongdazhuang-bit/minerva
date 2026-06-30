# Agent 对话消息附件 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Agent 对话附件从 `meta_json` 演进为独立表 `agent_message_attachment`，支持任意白名单文件上传（5MB）、S3/Local 存储、会话加载时按需刷新 `download_url`；仅图片 + MULTIMODAL 注入 vision；图片可点击放大预览。

**Architecture:** 单表 `agent_message_attachment` 绑定 `message_id`；上传走现有 `WorkspaceFileService`（前缀 `agent_attachment/`）；DB 不存 `download_url`，`GET session detail` 批量 `create_download_url`；删除 session/截断消息时应用层删存储对象再删行；vision 链路仅读 `kind=image` 行；历史 JSONB fallback 保留。

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, PostgreSQL, pytest（新建）, React 18, Ant Design `Image`/`Upload`, TanStack Query, i18next.

**Spec:** `docs/superpowers/specs/2026-06-30-agent-message-attachment-design.md`

---

## Scope Check

单个子系统：Agent 附件表化 + URL 刷新 + 通用上传 + 前端非图片展示与图片 preview。依赖已存在的 `WorkspaceFileService`、vision MVP 代码，不改动 `app/llm`、规则模块。

---

## File Structure

### Backend — 新建

| 路径 | 职责 |
|------|------|
| `backend/sql/patches/2026-06-30-agent-message-attachment.sql` | 建表 `agent_message_attachment` |
| `backend/app/agent/infrastructure/attachment_kind.py` | `kind` MIME 判定、通用 MIME 白名单解析 |
| `backend/tests/test_attachment_kind.py` | kind / MIME 单元测试 |
| `backend/tests/test_agent_attachment_service.py` | 校验逻辑单元测试 |

### Backend — 修改

| 路径 | 职责 |
|------|------|
| `backend/sql/schema_postgresql.sql` | 同步建表 DDL |
| `backend/app/agent/domain/db/models.py` | `AgentMessageAttachment` ORM |
| `backend/app/agent/infrastructure/repository.py` | attachment CRUD、session 删除扩展 |
| `backend/app/agent/service/agent_attachment_service.py` | 通用上传校验、run 解析、URL 刷新、存储删除 |
| `backend/app/agent/service/agent_graph_run_service.py` | 发送时写 attachment 行，停写 meta_json |
| `backend/app/agent/api/v2/schemas.py` | `id`/`kind` 字段、config 扩展 |
| `backend/app/agent/api/v2/router.py` | upload/config/session detail/download-url |
| `backend/app/config.py` | 四个 `AGENT_ATTACHMENT_*` 字段 |
| `backend/.env.example` | 注释块 |
| `backend/.env.dev` | 同步默认值 |

### Frontend — 新建 / 修改

| 路径 | 职责 |
|------|------|
| `frontend/src/features/agent/AgentAttachmentImage.tsx` | 图片缩略图 + `Image` preview 放大 |
| `frontend/src/features/agent/AgentAttachmentFile.tsx` | 非图片文件卡片 + 下载链接 |
| `frontend/src/features/agent/AgentsPage.tsx` | composer 任意类型、消息区拆分 image/file |
| `frontend/src/features/agent/AgentsPage.css` | 文件卡片样式 |
| `frontend/src/api/agent.ts` | 类型、`attachment_*` config、可选 refresh API |
| `frontend/src/i18n/locales/zh-CN.json` | 文案 |
| `frontend/src/i18n/locales/en.json` | 文案 |

### Docs（实现完成后）

| 路径 | 职责 |
|------|------|
| `docs/superpowers/specs/2026-06-30-agent-message-attachment-design.md` | 状态 → 已实现 + 实现对照 |

---

### Task 1: 数据库补丁与 ORM

**Files:**
- Create: `backend/sql/patches/2026-06-30-agent-message-attachment.sql`
- Modify: `backend/sql/schema_postgresql.sql`
- Modify: `backend/app/agent/domain/db/models.py`

- [ ] **Step 1: 编写 SQL 补丁**

`backend/sql/patches/2026-06-30-agent-message-attachment.sql`:

```sql
CREATE TABLE IF NOT EXISTS public.agent_message_attachment (
  id            UUID         NOT NULL,
  workspace_id  UUID         NOT NULL,
  session_id    UUID         NOT NULL,
  message_id    UUID         NOT NULL,
  object_key    VARCHAR(1024) NOT NULL,
  storage_kind  VARCHAR(16)  NOT NULL,
  file_name     VARCHAR(256) NULL,
  content_type  VARCHAR(128) NULL,
  size          BIGINT       NULL,
  kind          VARCHAR(16)  NOT NULL,
  created_by    UUID         NULL,
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  CONSTRAINT agent_message_attachment_pk PRIMARY KEY (id)
);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_workspace_id
  ON public.agent_message_attachment (workspace_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_session_id
  ON public.agent_message_attachment (session_id);
CREATE INDEX IF NOT EXISTS ix_agent_message_attachment_message_id
  ON public.agent_message_attachment (message_id);
COMMENT ON TABLE public.agent_message_attachment IS 'Agent 对话消息附件元数据（不含 download_url）';
COMMENT ON COLUMN public.agent_message_attachment.storage_kind IS '上传时快照: S3 / LOCAL / DEFAULT_LOCAL';
COMMENT ON COLUMN public.agent_message_attachment.kind IS 'image | file';
```

- [ ] **Step 2: 同步 `schema_postgresql.sql`**

将相同 DDL 追加到 agent 表区域（`agent_message` 之后）。

- [ ] **Step 3: 添加 ORM 模型**

`backend/app/agent/domain/db/models.py` 末尾追加：

```python
class AgentMessageAttachment(Base):
    """Agent 对话单条消息的附件元数据；逻辑关联 agent_message / agent_session。"""

    __tablename__ = "agent_message_attachment"
    __table_args__ = (
        Index("ix_agent_message_attachment_session_id", "session_id"),
        Index("ix_agent_message_attachment_message_id", "message_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True, nullable=False)
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    storage_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    file_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    content_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    size: Mapped[int | None] = mapped_column(sa.BIGINT, nullable=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=text("now()"), nullable=False
    )
```

- [ ] **Step 4: 本地执行补丁**

Run: `psql $DATABASE_URL -f backend/sql/patches/2026-06-30-agent-message-attachment.sql`  
Expected: `CREATE TABLE` 成功（已存在则跳过）

- [ ] **Step 5: Commit**

```bash
git add backend/sql/patches/2026-06-30-agent-message-attachment.sql backend/sql/schema_postgresql.sql backend/app/agent/domain/db/models.py
git commit -m "feat(agent): add agent_message_attachment table and ORM"
```

---

### Task 2: 环境变量与 attachment kind 工具

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`
- Create: `backend/app/agent/infrastructure/attachment_kind.py`
- Create: `backend/tests/test_attachment_kind.py`

- [ ] **Step 1: 写失败测试**

`backend/tests/test_attachment_kind.py`:

```python
from app.agent.infrastructure.attachment_kind import (
    allowed_attachment_mime_set,
    attachment_kind_from_mime,
)


def test_attachment_kind_image():
    assert attachment_kind_from_mime("image/png") == "image"
    assert attachment_kind_from_mime("application/pdf") == "file"


def test_allowed_attachment_mime_set_parses_csv():
    raw = "image/png, application/pdf ,text/plain"
    assert allowed_attachment_mime_set(raw) == {"image/png", "application/pdf", "text/plain"}
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_attachment_kind.py -v`  
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 `attachment_kind.py`**

```python
"""Attachment MIME whitelist and kind classification."""

from __future__ import annotations


def allowed_attachment_mime_set(raw: str) -> set[str]:
    """Parse comma-separated MIME whitelist from settings."""

    return {part.strip().lower() for part in (raw or "").split(",") if part.strip()}


def attachment_kind_from_mime(content_type: str | None) -> str:
    """Return ``image`` when MIME starts with image/; else ``file``."""

    mime = (content_type or "").strip().lower()
    return "image" if mime.startswith("image/") else "file"
```

- [ ] **Step 4: 在 `config.py` 追加字段（约 `agent_vision_image_*` 之后）**

```python
    agent_attachment_max_count: int = Field(
        default=5,
        ge=1,
        le=20,
        validation_alias=AliasChoices("AGENT_ATTACHMENT_MAX_COUNT", "agent_attachment_max_count"),
    )
    agent_attachment_max_bytes: int = Field(
        default=5242880,
        ge=1,
        validation_alias=AliasChoices("AGENT_ATTACHMENT_MAX_BYTES", "agent_attachment_max_bytes"),
    )
    agent_attachment_allowed_mime: str = Field(
        default=(
            "image/jpeg,image/jpg,image/png,image/gif,image/webp,"
            "application/pdf,text/plain,text/csv,"
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        validation_alias=AliasChoices("AGENT_ATTACHMENT_ALLOWED_MIME", "agent_attachment_allowed_mime"),
    )
    agent_attachment_download_expires_in: int = Field(
        default=3600,
        ge=60,
        le=86400,
        validation_alias=AliasChoices(
            "AGENT_ATTACHMENT_DOWNLOAD_EXPIRES_IN",
            "agent_attachment_download_expires_in",
        ),
    )
```

- [ ] **Step 5: 更新 `.env.example` 与 `.env.dev`**

```bash
# AGENT_ATTACHMENT_MAX_COUNT=5
# AGENT_ATTACHMENT_MAX_BYTES=5242880
# AGENT_ATTACHMENT_ALLOWED_MIME=image/jpeg,image/png,...
# AGENT_ATTACHMENT_DOWNLOAD_EXPIRES_IN=3600
```

- [ ] **Step 6: 运行测试**

Run: `cd backend && python -m pytest tests/test_attachment_kind.py -v`  
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add backend/app/config.py backend/.env.example backend/.env.dev backend/app/agent/infrastructure/attachment_kind.py backend/tests/test_attachment_kind.py
git commit -m "feat(agent): add attachment env settings and kind helpers"
```

---

### Task 3: Repository — attachment CRUD

**Files:**
- Modify: `backend/app/agent/infrastructure/repository.py`

- [ ] **Step 1: 添加 insert / list / delete 函数**

在 `repository.py` 追加：

```python
async def insert_agent_message_attachments(
    session: AsyncSession,
    *,
    rows: list[AgentMessageAttachment],
) -> list[AgentMessageAttachment]:
    """批量插入消息附件行。"""

    for row in rows:
        session.add(row)
    await session.flush()
    return rows


async def list_attachments_for_session(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
) -> list[AgentMessageAttachment]:
    """按 session 加载全部附件行（按 created_at 排序）。"""

    stmt = (
        select(AgentMessageAttachment)
        .where(AgentMessageAttachment.session_id == session_id)
        .order_by(AgentMessageAttachment.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def list_attachments_for_message_ids(
    session: AsyncSession,
    *,
    message_ids: list[uuid.UUID],
) -> list[AgentMessageAttachment]:
    """批量按 message_id 加载附件。"""

    if not message_ids:
        return []
    stmt = (
        select(AgentMessageAttachment)
        .where(AgentMessageAttachment.message_id.in_(message_ids))
        .order_by(AgentMessageAttachment.created_at.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def delete_attachments_for_session(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
) -> list[AgentMessageAttachment]:
    """删除 session 下全部附件行并返回被删行（供存储清理）。"""

    rows = await list_attachments_for_session(session, session_id=session_id)
    if rows:
        await session.execute(
            delete(AgentMessageAttachment).where(
                AgentMessageAttachment.session_id == session_id
            )
        )
    return rows


async def delete_attachments_for_messages_from_seq(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    from_seq: int,
) -> list[AgentMessageAttachment]:
    """删除 seq >= from_seq 的消息关联附件，返回被删行。"""

    msg_ids = list(
        (
            await session.execute(
                select(AgentMessage.id).where(
                    AgentMessage.session_id == session_id,
                    AgentMessage.seq >= from_seq,
                )
            )
        ).scalars().all()
    )
    if not msg_ids:
        return []
    stmt = select(AgentMessageAttachment).where(
        AgentMessageAttachment.message_id.in_(msg_ids)
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if rows:
        await session.execute(
            delete(AgentMessageAttachment).where(
                AgentMessageAttachment.message_id.in_(msg_ids)
            )
        )
    return rows
```

- [ ] **Step 2: 扩展 `delete_agent_session`**

在删除 `AgentMessage` **之前**插入：

```python
        attachment_rows = await delete_attachments_for_session(
            session, session_id=session_id
        )
        # 注：存储对象删除在 service 层调用（Task 5），repository 只返回 rows 或通过 callback；
        # 此处先删 DB 行，service 包装 delete_agent_session 时先取 rows 再删对象。
```

**调整**：将 `delete_agent_session` 改为先 `list_attachments_for_session` 返回给 caller，或由 `agent_attachment_service.delete_storage_for_rows` 在 router/service 调用。更简单做法：在 `delete_agent_session` 开头：

```python
    attachment_rows = await list_attachments_for_session(session, session_id=session_id)
    ...
    await delete_attachments_for_session(session, session_id=session_id)
```

并在 router 的 delete endpoint 或 repository 上层调用 storage 删除（Task 5）。

- [ ] **Step 3: Commit**

```bash
git add backend/app/agent/infrastructure/repository.py
git commit -m "feat(agent): attachment repository CRUD and session delete hooks"
```

---

### Task 4: 重构 `agent_attachment_service`

**Files:**
- Modify: `backend/app/agent/service/agent_attachment_service.py`
- Create: `backend/tests/test_agent_attachment_service.py`

- [ ] **Step 1: 常量与前缀**

```python
AGENT_ATTACHMENT_MODULE_PREFIX = "agent_attachment"
LEGACY_AGENT_VISION_PREFIX = "agent_vision"  # 只读兼容


def assert_agent_attachment_object_key(object_key: str) -> str:
    key = (object_key or "").strip()
    if key.startswith(f"{AGENT_ATTACHMENT_MODULE_PREFIX}/"):
        return key
    if key.startswith(f"{LEGACY_AGENT_VISION_PREFIX}/"):
        return key
    raise AppError("agent.attachment_invalid", "Invalid attachment object_key", 422)
```

- [ ] **Step 2: 通用上传校验 `validate_attachment_upload_payload`**

- 大小 ≤ `settings.agent_attachment_max_bytes`
- MIME ∈ `allowed_attachment_mime_set(settings.agent_attachment_allowed_mime)`
- 扩展名白名单（图片沿用 vision 扩展名；PDF/doc 等追加映射表或宽松校验）

- [ ] **Step 3: `resolve_attachment_meta_for_run` 改造**

- 上限改用 `agent_attachment_max_count`
- 接受 `agent_attachment/` 与 legacy `agent_vision/`
- **不再**在 resolved dict 中包含 `download_url`（vision 跑图只用 object_key）
- 若有 `kind=image` 附件，额外校验 vision MIME 子集 + `agent_vision_image_max_count`（LLM 注入张数）

- [ ] **Step 4: 新增 `build_attachment_rows_for_message`**

```python
async def build_attachment_rows_for_message(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
    created_by: uuid.UUID | None,
    items: list[dict],
) -> list[AgentMessageAttachment]:
    """从 run 校验后的 items 创建 ORM 行（含 storage_kind 快照）。"""

    active = await resolve_active_storage(session, workspace_id=workspace_id)
    storage_kind = active.kind
    rows: list[AgentMessageAttachment] = []
    for item in items:
        rows.append(
            AgentMessageAttachment(
                workspace_id=workspace_id,
                session_id=session_id,
                message_id=message_id,
                object_key=item["object_key"],
                storage_kind=storage_kind,
                file_name=item.get("file_name"),
                content_type=item.get("content_type"),
                size=item.get("size"),
                kind=attachment_kind_from_mime(item.get("content_type")),
                created_by=created_by,
            )
        )
    return rows
```

- [ ] **Step 5: 新增 `refresh_attachment_download_urls`**

```python
async def attachment_rows_to_api_out(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    rows: list[AgentMessageAttachment],
) -> list[dict]:
    """为 DB 行 mint fresh download_url（不入库）。"""

    file_service = WorkspaceFileService(session=session)
    expires = settings.agent_attachment_download_expires_in
    out: list[dict] = []
    for row in rows:
        url = await file_service.create_download_url(
            workspace_id=workspace_id,
            object_key=row.object_key,
            presign_expires_in=expires,
        )
        out.append(
            {
                "id": row.id,
                "object_key": row.object_key,
                "file_name": row.file_name,
                "content_type": row.content_type,
                "size": row.size,
                "kind": row.kind,
                "download_url": url,
            }
        )
    return out
```

- [ ] **Step 6: 新增 `delete_storage_objects_for_rows`**

按 `storage_kind` 调用 S3FileService.delete_file 或 LocalFileService.delete_file（需确认 local 已有 delete；若无则 proxy 删除 gateway 文件）。

- [ ] **Step 7: 单元测试**

测试 object_key 前缀校验、kind 判定、legacy 前缀接受。

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(agent): general attachment service with URL refresh helpers"
```

---

### Task 5: Run 持久化 — 写 attachment 表

**Files:**
- Modify: `backend/app/agent/service/agent_graph_run_service.py`

- [ ] **Step 1: 发送用户消息时**

将：

```python
meta_json={"attachments": run_attachments} if run_attachments else None,
```

改为：

```python
meta_json=None,
```

并在 `user_row` 创建后：

```python
if run_attachments:
    attachment_rows = await build_attachment_rows_for_message(
        session,
        workspace_id=workspace_id,
        session_id=session_id,
        message_id=user_row.id,
        created_by=triggered_by,
        items=run_attachments,
    )
    await agent_repo.insert_agent_message_attachments(session, rows=attachment_rows)
```

- [ ] **Step 2: regenerate 附件来源**

从 `meta_json` 改为：查最近 user message 的 attachment 表行，或 regenerate 目标 user 消息的 attachment 行。

- [ ] **Step 3: `run_attachments` 注入 GraphState**

仅 `kind=image` 的项传入 `user_attachments`（vision 用）。

- [ ] **Step 4: 消息截断时删存储**

在 `delete_agent_messages_from_seq` 调用前后，调用 `delete_attachments_for_messages_from_seq` + `delete_storage_objects_for_rows`。

- [ ] **Step 5: Commit**

```bash
git commit -m "feat(agent): persist attachments to table on run"
```

---

### Task 6: Session 删除存储清理

**Files:**
- Modify: `backend/app/agent/infrastructure/repository.py`
- Modify: `backend/app/agent/api/v2/router.py`

- [ ] **Step 1: 在 `delete_agent_session` repository 或 router 中**

```python
attachment_rows = await list_attachments_for_session(db, session_id=session_id)
await delete_storage_objects_for_rows(db, workspace_id=workspace_id, rows=attachment_rows)
deleted = await agent_repo.delete_agent_session(...)
```

确保 DB 行在 `delete_agent_session` 内已清理（Task 3）。

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(agent): delete attachment storage on session remove"
```

---

### Task 7: API — config / upload / session detail

**Files:**
- Modify: `backend/app/agent/api/v2/schemas.py`
- Modify: `backend/app/agent/api/v2/router.py`

- [ ] **Step 1: 扩展 schemas**

`AgentV2ConfigOut` 增加：

```python
    attachment_max_count: int
    attachment_max_bytes: int
    attachment_allowed_mime: list[str]
```

`AgentMessageAttachmentOut` 增加：

```python
    id: uuid.UUID | None = None
    kind: str = "file"
```

- [ ] **Step 2: config endpoint**

填充新字段 + 保留 `vision_image_*`。

- [ ] **Step 3: upload endpoint**

- `module_prefix=AGENT_ATTACHMENT_MODULE_PREFIX`
- 使用 `validate_attachment_upload_payload`
- 错误码改为 `agent.attachment_*`

- [ ] **Step 4: session detail 刷新 URL**

```python
    all_msg_ids = [m.id for m in msg_rows]
    att_rows = await agent_repo.list_attachments_for_message_ids(db, message_ids=all_msg_ids)
    att_by_msg: dict[uuid.UUID, list] = {}
    for row in att_rows:
        att_by_msg.setdefault(row.message_id, []).append(row)

    file_service_rows = await attachment_rows_to_api_out(db, workspace_id=workspace_id, rows=att_rows)
    # 重新按 message 分组 mapped dicts
```

每条 message：

```python
        db_attachments = att_by_msg.get(m.id, [])
        if db_attachments:
            attachments = await attachment_rows_to_api_out(...)  # 或批量后 slice
        else:
            attachments = await _legacy_attachments_from_meta_with_refresh(...)
```

Legacy fallback：解析 `meta_json.attachments`，对每项调 `create_download_url`（无 `id`）。

- [ ] **Step 5: 可选 `GET /attachments/{attachment_id}/download-url`**

鉴权：attachment.workspace_id == workspace_id。

- [ ] **Step 6: Commit**

```bash
git commit -m "feat(agent): attachment config, upload, and session URL refresh APIs"
```

---

### Task 8: chat_history vision 仅 image

**Files:**
- Modify: `backend/app/agent/infrastructure/chat_history.py`

- [ ] **Step 1: 历史重建时**

从 attachment 表加载（若 message 有行），否则 fallback meta_json；`build_vision_human_message` 仅传入 `kind=image` 项。

- [ ] **Step 2: Commit**

```bash
git commit -m "feat(agent): chat history vision from attachment table"
```

---

### Task 9: 前端 — 通用上传与非图片展示

**Files:**
- Modify: `frontend/src/api/agent.ts`
- Create: `frontend/src/features/agent/AgentAttachmentImage.tsx`
- Create: `frontend/src/features/agent/AgentAttachmentFile.tsx`
- Modify: `frontend/src/features/agent/AgentsPage.tsx`
- Modify: `frontend/src/features/agent/AgentsPage.css`
- Modify: `frontend/src/i18n/locales/zh-CN.json`
- Modify: `frontend/src/i18n/locales/en.json`

- [ ] **Step 1: API 类型扩展**

```typescript
export type AgentV2Config = {
  // ...
  attachment_max_count: number
  attachment_max_bytes: number
  attachment_allowed_mime: string[]
}

export type AgentMessageAttachmentOut = {
  id?: string
  object_key: string
  file_name?: string | null
  content_type?: string | null
  size?: number | null
  kind?: 'image' | 'file'
  download_url?: string | null
}
```

- [ ] **Step 2: Composer 上传 accept**

使用 `agentV2Config.attachment_allowed_mime` 生成 `accept`；大小校验用 `attachment_max_bytes`；数量用 `attachment_max_count`。

- [ ] **Step 3: `AgentAttachmentImage.tsx`**

```tsx
import { Image } from 'antd'
import { resolveAgentAttachmentUrl } from '@/api/agent'

export function AgentAttachmentImage({ att }: { att: AgentMessageAttachmentOut }) {
  const src = resolveAgentAttachmentUrl(att.download_url)
  if (!src) return null
  return (
    <Image
      rootClassName="agents-page__msg-attachment-wrap"
      className="agents-page__msg-attachment-img"
      src={src}
      alt={att.file_name ?? ''}
      preview={{ mask: true }}
    />
  )
}
```

消息区多图时使用 `Image.PreviewGroup`。

- [ ] **Step 4: `AgentAttachmentFile.tsx`**

非图片：文件名 + `Link`/`Button` 打开 `download_url`（新标签下载）。

- [ ] **Step 5: `AgentsPage` 消息渲染**

```tsx
{m.attachments?.map((att) =>
  att.kind === 'image' || att.content_type?.startsWith('image/') ? (
    <AgentAttachmentImage key={att.id ?? att.object_key} att={att} />
  ) : (
    <AgentAttachmentFile key={att.id ?? att.object_key} att={att} />
  )
)}
```

- [ ] **Step 6: i18n**

`agents.attachment.fileDownload`、`agents.attachment.tooLarge`、`agents.attachment.previewFailed` 等。

- [ ] **Step 7: 手动验证**

1. 上传 PNG → 发送 → 点击缩略图放大  
2. 上传 PDF → 发送 → 显示文件卡片可下载  
3. 刷新页面 → 图片仍显示（URL 已刷新）  
4. 等待超过旧 token 过期时间 → 重新进入会话 → 图片恢复  

- [ ] **Step 8: Commit**

```bash
git commit -m "feat(agent): general attachment UI with image preview"
```

---

### Task 10: Spec 回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-30-agent-message-attachment-design.md`

- [ ] **Step 1: 更新状态与实现对照**

文首状态 → **已实现（YYYY-MM-DD）**  
追加章节 **实现对照（以代码为准）** 表格。

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-06-30-agent-message-attachment-design.md
git commit -m "docs: mark agent message attachment spec as implemented"
```

---

## Plan Self-Review

| Spec 章节 | 对应 Task |
|-----------|-----------|
| §2 数据模型 | Task 1 |
| §4 环境变量 | Task 2 |
| §5 API | Task 7 |
| §6 删除 | Task 3, 5, 6 |
| §7 Vision 仅图片 | Task 5, 8 |
| §8 前端 + 放大预览 | Task 9 |
| §9 错误码 | Task 4, 7 |
| JSONB fallback | Task 7 Step 4 |

无 TBD / 占位步骤；类型名 `AgentMessageAttachment`、`attachment_kind_from_mime` 全文一致。

---

## Manual Test Checklist

- [ ] S3 工作区：upload PDF + PNG，session detail 返回 fresh URL
- [ ] Local 工作区：同上
- [ ] 5MB+1 字节 → 422 `agent.attachment_file_too_large`
- [ ] 非 MULTIMODAL + 仅 PDF → run 成功，无 vision 调用
- [ ] 非 MULTIMODAL + PNG → 422
- [ ] 删 session → 存储对象不可再 download
- [ ] 图片点击 Ant Design preview 放大
- [ ] 旧会话（仅 meta_json）仍可展示并刷新 URL
