# Agent 对话消息附件（通用文件 + 按需刷新 URL）

**日期**：2026-06-30  
**状态**：已实现（2026-06-30）  
**范围**：Agent 对话中支持任意类型文件上传（MIME/大小白名单）；新建 `agent_message_attachment` 表与消息关联；复用 S3 / Local 存储；**DB 不持久化 `download_url`**，会话加载时按需刷新 token；仅 **图片 + MULTIMODAL** 注入 LLM vision；图片附件支持**点击放大预览**。

**前置 / 关联文档**：

- `docs/superpowers/specs/2026-06-30-agent-vision-image-upload-design.md`（vision MVP；本期演进为通用附件表 + URL 刷新）
- `docs/superpowers/specs/2026-06-30-file-storage-local-design.md`（`resolve_active_storage`、S3/Local 双轨）
- `docs/superpowers/specs/2026-04-30-s3-file-storage-design.md`（S3 object key 规则）

---

## 1. 目标与成功标准

### 1.1 目标

- 用户在 Agent 对话 composer 可上传**任意白名单内**文件（不限于图片）。
- 附件与**单条用户消息**绑定，持久化于独立表 `agent_message_attachment`。
- 文件字节写入工作区活跃存储（S3 / Local / DEFAULT_LOCAL），经 `WorkspaceFileService` 统一路由。
- 历史会话展示附件时，后端**每次请求**为附件生成 fresh `download_url`（S3 预签名 / Local JWT），避免链接过期导致裂图。
- **图片**在 MULTIMODAL 模型下继续走 vision 全链路；**非图片**仅展示与下载，不注入 LLM。
- 消息气泡内**图片缩略图可点击**，打开放大预览（lightbox）。

### 1.2 成功标准

- 上传、发送、会话详情、历史 replay 在 S3 与 Local 存储下均正常。
- 会话详情 API 返回的 `download_url` 在 `AGENT_ATTACHMENT_DOWNLOAD_EXPIRES_IN` 内有效；重新拉取会话后图片可恢复显示。
- 单条消息附件数、单文件 5MB、MIME 白名单校验生效。
- 删除 session 或截断消息时，应用层清理 attachment 行及存储对象。
- 图片点击后全屏/模态放大预览，支持关闭返回对话。

### 1.3 需求决策摘要

| 项 | 决策 |
|----|------|
| 文件类型（上传） | 任意类型，受 MIME + 大小白名单约束 |
| 关联模型 | **消息级**（每条 `agent_message` 0..N 附件） |
| 表结构 | 单表 **`agent_message_attachment`**（方案 A） |
| URL 策略 | **按需刷新 token**；DB **不存** `download_url` |
| LLM 注入 | **仅图片** + 模型含 `MULTIMODAL` |
| 单文件上限 | **5MB**（`AGENT_ATTACHMENT_MAX_BYTES=5242880`） |
| 存储前缀 | **`agent_attachment/`**（新上传；旧 `agent_vision/` 只读兼容） |
| 图片 UI | 缩略图 + **点击放大预览**（Ant Design `Image` 或等价 lightbox） |

### 1.4 非目标（本期）

- 非图片文件的 LLM 文本提取 / OCR / RAG 注入。
- 跨消息复用同一文件（会话级文件库）。
- 附件版本管理、在线编辑。
- 批量迁移历史 `agent_vision/` object_key 至新前缀（兼容读取即可）。

---

## 2. 数据模型

### 2.1 表 `agent_message_attachment`

| 列 | 类型 | 说明 |
|----|------|------|
| `id` | UUID PK | 附件 ID（API 对外暴露） |
| `workspace_id` | UUID, index | 工作区（冗余，权限校验） |
| `session_id` | UUID, index | 逻辑关联 `agent_session.id` |
| `message_id` | UUID, index | 逻辑关联 `agent_message.id` |
| `object_key` | varchar(1024) | 如 `agent_attachment/2026/06/{uuid}.png` |
| `storage_kind` | varchar(16) | 上传时快照：`S3` / `LOCAL` / `DEFAULT_LOCAL` |
| `file_name` | varchar(256) | 原始文件名 |
| `content_type` | varchar(128) | MIME |
| `size` | bigint | 字节数 |
| `kind` | varchar(16) | `image` \| `file`（由 MIME 判定；仅 `image` 可走 vision） |
| `created_by` | UUID, nullable | 上传者 |
| `created_at` | timestamptz | 创建时间 |

**约定（Minerva）**：

- 无数据库外键；UUID 列 + 索引；关联在注释 / service 层维护。
- 删除顺序（应用层）：attachment 存储对象 → `agent_message_attachment` 行 → 消息 / 会话（见 §6）。

### 2.2 与 `meta_json.attachments` 的关系

| 场景 | 行为 |
|------|------|
| 新上传 + 发送 | 只写 `agent_message_attachment`，**不写** `meta_json.attachments` |
| 历史会话（仅 JSONB） | 会话详情 API **fallback** 解析 `meta_json.attachments`，并刷新 URL |
| 可选迁移补丁 | 将存量 JSONB 回填新表（非 MVP 阻塞项） |

### 2.3 `kind` 判定

- `content_type` 以 `image/` 开头 → `kind=image`
- 否则 → `kind=file`

Vision 跑图与 `MULTIMODAL` 校验仅针对 `kind=image` 的附件。

---

## 3. 存储

- **`module_prefix`**：`agent_attachment`（替代新上传的 `agent_vision`）。
- 复用 `WorkspaceFileService.upload_file` / `read_object_bytes` / `create_download_url`。
- **`storage_kind`** 在上传时由 `resolve_active_storage` 快照写入 DB，删除与读取时使用快照对应后端，避免工作区切换存储后旧附件不可达。

---

## 4. 环境变量

| 字段 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `agent_attachment_max_count` | `AGENT_ATTACHMENT_MAX_COUNT` | `5` | 单条消息最多附件数 |
| `agent_attachment_max_bytes` | `AGENT_ATTACHMENT_MAX_BYTES` | `5242880` | 单文件上限 **5MB** |
| `agent_attachment_allowed_mime` | `AGENT_ATTACHMENT_ALLOWED_MIME` | 见下 | 逗号分隔 MIME 白名单 |
| `agent_attachment_download_expires_in` | `AGENT_ATTACHMENT_DOWNLOAD_EXPIRES_IN` | `3600` | 刷新 URL 有效期（秒） |

**默认 MIME 白名单**：

```text
image/jpeg,image/jpg,image/png,image/gif,image/webp,
application/pdf,
text/plain,text/csv,
application/vnd.openxmlformats-officedocument.wordprocessingml.document,
application/vnd.openxmlformats-officedocument.spreadsheetml.sheet
```

Vision LLM 注入仍受现有 **`AGENT_VISION_IMAGE_*`** 约束（更严格的图片 MIME/数量，默认 1 张）。  
同步更新 `backend/.env.example` 与 `backend/.env.dev`。

---

## 5. API

### 5.1 上传

| 项 | 值 |
|----|-----|
| 方法 / 路径 | `POST /workspaces/{workspace_id}/agent/v2/attachments:upload` |
| Body | `multipart/form-data`，字段 `file` |
| 权限 | `get_current_user` + `require_workspace_member` |

校验：MIME ∈ 白名单、大小 ≤ 5MB、扩展名与 MIME 双重校验（沿用/扩展现有校验逻辑）。

响应（上传时生成一次短效 URL 供 composer 预览）：

```python
class AgentAttachmentUploadOut(BaseModel):
    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str
```

**上传阶段不写 DB**；附件行在用户消息发送成功后插入。

### 5.2 Run 发送（持久化）

`POST .../sessions/{session_id}/runs` 请求体：

```python
class AgentAttachmentIn(BaseModel):
    object_key: str
    file_name: str | None = None
    content_type: str | None = None

class AgentRunCreateV2(BaseModel):
    attachments: list[AgentAttachmentIn] = Field(default_factory=list)
    # ... 现有字段不变 ...
```

流程：

1. `len(attachments) ≤ agent_attachment_max_count`
2. 每个 `object_key` 前缀 `agent_attachment/`（兼容读取 `agent_vision/` 仅用于历史 fallback）
3. 对象存在 + MIME/大小复检
4. 若有 `kind=image` 附件，模型须含 `MULTIMODAL`（沿用 vision 校验）
5. 写入用户 `agent_message` + 批量插入 `agent_message_attachment`（含 `storage_kind` 快照）

### 5.3 会话详情（URL 刷新）

`GET .../sessions/{session_id}`：对每个 attachment 调用 `WorkspaceFileService.create_download_url(..., presign_expires_in=agent_attachment_download_expires_in)`，填入响应。

```python
class AgentMessageAttachmentOut(BaseModel):
    id: uuid.UUID
    object_key: str
    file_name: str | None
    content_type: str | None
    size: int | None
    kind: str  # image | file
    download_url: str  # 每次请求 freshly minted，不入库
```

**Fallback**：若新表无行且 `meta_json.attachments` 非空，解析 JSONB 并同样刷新 URL（无 `id` 时可省略或使用 synthetic id）。

### 5.4 单附件 URL 刷新（可选）

| 项 | 值 |
|----|-----|
| 路径 | `GET .../agent/v2/attachments/{attachment_id}/download-url` |
| 响应 | `{ download_url: str }` |

用于大图懒加载或前端检测到 401/403 后单条刷新。

### 5.5 下载

| 项 | 值 |
|----|-----|
| 路径 | `GET .../agent/v2/attachments/{attachment_id}:download` |
| 行为 | 鉴权 → `302` 至 fresh presigned URL，或 `?mode=proxy` 流式输出 |

### 5.6 `GET /agent/v2/config` 扩展

```python
class AgentV2ConfigOut(BaseModel):
    # ... 现有字段 ...
    attachment_max_count: int
    attachment_max_bytes: int
    attachment_allowed_mime: list[str]
    # vision_image_* 保留，用于 composer 提示与 vision 子集校验
```

---

## 6. 删除策略（应用层）

| 触发场景 | 清理顺序 |
|----------|----------|
| 删除 `agent_session` | 查 session 下全部 attachment → 按 `storage_kind` 删存储对象 → 删 attachment 行 → 现有 session 级联删除 |
| Run 编辑重发（seq 截断） | 被删 message 的 attachment 行 + 对应存储对象 |
| 实现入口 | 扩展 `delete_agent_session` 与消息截断逻辑 |

---

## 7. 跑图与 Vision（仅图片）

- `GraphState.user_attachments` 仅注入 `kind=image` 的元数据（含 `object_key`，**不用** `download_url` 调模型）。
- `VisionMessageBuilder` / Planner / SubAgent / Synthesizer 行为与 vision MVP 一致。
- 非图片附件不参与 `build_vision_human_message`。
- 历史 replay：非 MULTIMODAL 模型对用户消息仅保留文本 part。

---

## 8. 前端

### 8.1 Composer

- 读取 `attachment_max_count/bytes/allowed_mime`；支持选择白名单内任意文件。
- 上传 → 本地 state 保存 `object_key` + 短效 `download_url` 预览。
- 发送 run 时传 `attachments` 元数据，不传 base64。

### 8.2 消息气泡

| `kind` | 展示 |
|--------|------|
| `image` | 缩略图（`download_url`）；**点击打开放大预览** |
| `file` | 文件名 + 下载链接 / 图标 |

### 8.3 图片放大预览

- 使用 Ant Design **`Image`** 组件（`preview` 配置）或 **`Image.PreviewGroup`**（同条消息多图可左右切换）。
- 点击缩略图 → 全屏/模态预览，支持缩放、关闭。
- `download_url` 过期导致预览失败时：重新请求会话详情或 `download-url` 接口刷新后再打开。
- 样式与 `AgentsPage` 现有气泡布局一致，缩略图 max-height 限制避免撑破布局。

### 8.4 i18n

- 上传失败、超限、MIME 拒绝、预览加载失败等文案 `zh-CN` / `en`。

---

## 9. 错误码

| code | HTTP | 场景 |
|------|------|------|
| `agent.attachment_limit` | 422 | 超过 max_count |
| `agent.attachment_invalid` | 422 | object_key 非法或对象不存在 |
| `agent.attachment_mime_not_allowed` | 422 | MIME 不在白名单 |
| `agent.attachment_file_too_large` | 422 | 超过 5MB |
| `agent.attachment_not_found` | 404 | 附件 ID 不存在 |
| `agent.model_vision_not_supported` | 422 | 非 MULTIMODAL + image 附件 |

旧 `agent.vision_*` 可在实现期映射为 `agent.attachment_*` 或保留 alias。

---

## 10. 架构与目录（建议）

```text
backend/sql/patches/
  2026-06-30-agent-message-attachment.sql

backend/app/agent/
  domain/db/models.py              # AgentMessageAttachment ORM
  infrastructure/repository.py     # attachment CRUD + session 清理
  service/agent_attachment_service.py  # 校验、kind 判定、URL 刷新
  api/v2/schemas.py                # AttachmentOut 扩展 id/kind
  api/v2/router.py                 # download-url、:download
  service/agent_graph_run_service.py   # 发送时写 attachment 行

frontend/src/features/agent/
  AgentsPage.tsx                   # 非图片展示
  AgentAttachmentImage.tsx       # 缩略图 + Image preview 放大
  agentSkillUi.ts                  # 如有共用类型
frontend/src/api/agent.ts
frontend/src/i18n/locales/*.json
```

---

## 11. 数据流

```text
[Upload]   file → WorkspaceFileService(agent_attachment/) → object_key + 短效 download_url（composer 预览）
[Run]      attachments → 校验 → agent_message + agent_message_attachment 行（无 download_url）
[Detail]   读 attachment 行 → create_download_url × N → 响应带 fresh URL
[UI img]   缩略图 src=download_url；点击 → Ant Design Image preview 放大
[UI file]  下载链接 href=download_url
[LLM]      仅 kind=image → VisionMessageBuilder → base64 data URL
[Delete]   删对象 → 删 attachment 行
```

---

## 12. 测试要点

- 单元：`kind` MIME 判定；URL 刷新 batch；5MB 边界。
- 集成：upload + run + session detail 返回 fresh URL；S3 / Local 各一条。
- 集成：非 MULTIMODAL + image → 422；PDF 附件 + MULTIMODAL → run 成功但不注入 vision。
- 集成：删 session 清理 storage + DB 行。
- 前端：图片点击放大；多图 PreviewGroup；URL 过期后 re-fetch 恢复。

---

## 13. 实现顺序建议

1. SQL 补丁 + ORM + repository  
2. Settings + config API + 上传校验扩展（`agent_attachment` 前缀）  
3. Run 持久化写 attachment 表；会话详情 URL 刷新  
4. 删除 cascade；可选 download-url / :download API  
5. Vision 链路改为读 attachment 表（保留 JSONB fallback）  
6. 前端：通用附件 UI + `AgentAttachmentImage` 放大预览 + i18n  
7. 测试与 spec 实现对照回填  

---

## 实现对照（以代码为准，2026-06-30）

| Spec 条目 | 代码位置 | 备注 |
|-----------|----------|------|
| `agent_message_attachment` 表 | `backend/sql/patches/2026-06-30-agent-message-attachment.sql` | |
| ORM | `backend/app/agent/domain/db/models.py` → `AgentMessageAttachment` | |
| 环境变量 | `backend/app/config.py` | 5MB 上限 |
| 上传 `agent_attachment/` | `agent_attachment_service.py`, `router.py` upload | legacy `agent_vision/` 可读 |
| Run 写表、不写 meta_json | `agent_graph_run_service.py` | |
| Session detail URL 刷新 | `router.py` → `_attachments_for_message_out` | JSONB fallback |
| 删除存储 + DB | `router.py` delete session; run 截断 | |
| Vision 仅 image | `chat_history.py`, `agent_graph_run_service.py` | |
| 前端通用附件 + preview | `AgentAttachmentImage.tsx`, `AgentsPage.tsx` | Ant Design `Image.PreviewGroup` |
| 单元测试 | `backend/tests/test_attachment_kind.py`, `test_agent_attachment_service.py` | 6 passed |
