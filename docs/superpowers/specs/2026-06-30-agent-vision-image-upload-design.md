# Agent 多模态图片上传设计

**日期**：2026-06-30  
**状态**：已实现（2026-06-30）  
**范围**：在 Agent 对话模块为标签含 **`MULTIMODAL`** 的模型支持图片上传与解析；图片经工作区已配置的存储策略（S3 / Local / DEFAULT_LOCAL）持久化；跑图全链路（Planner、Executor 子 Agent、Synthesizer）可见图片；**平时以 URL 元数据流转，仅在上游模型调用边界转为 base64 data URL**。

**关联文档**：

- `docs/superpowers/specs/2026-06-01-agent-chat-tag-filter-design.md`（Agent 选模与 `CHAT` tag；本期扩展为 `CHAT` **或** `MULTIMODAL`）
- `docs/superpowers/specs/2026-06-30-file-storage-local-design.md`（`resolve_active_storage`、S3/Local 双轨）
- `docs/superpowers/specs/2026-04-30-s3-file-storage-design.md`（S3 对象 key 规则）
- `docs/superpowers/specs/2026-05-28-model-provider-tags-design.md`（`MODEL_TAG` 字典体系）

---

## 1. 目标与成功标准

### 1.1 目标

- 管理员为模型勾选 **`MULTIMODAL`** 后，Agent 对话页可选该模型，composer 出现图片上传入口。
- 用户上传图片 → 写入工作区活跃存储 → 获得 **`object_key` + `download_url`**；发送消息时引用附件，**不传 base64**。
- Agent 跑图时 Planner、各 Skill 子 Agent、Synthesizer 在调用 LLM 前将附件转为 OpenAI 兼容 **content parts**（含 base64 `image_url`）。
- 会话历史持久化附件元数据（含 `download_url`），前端可展示缩略图；历史重放走与实时 run 相同的模型边界转换逻辑。
- 上传数量、单张大小、允许 MIME 由 **环境变量** 配置，并通过 `GET /agent/v2/config` 下发前端。

### 1.2 成功标准

- 工作区启用 S3 或 Local 存储时，上传与读取均正常；无启用项时回退 `DEFAULT_LOCAL`（与 `resolve_active_storage` 一致）。
- 选中 `MULTIMODAL` 模型时可上传 `.jpg`/`.jpeg`/`.png`；选中仅 `CHAT` 模型时无上传入口。
- 单次 run 附件数不超过 `AGENT_VISION_IMAGE_MAX_COUNT`（默认 1）；超限或 MIME/大小不合规返回 422。
- 对非 `MULTIMODAL` 模型携带 `attachments` 发起 run 返回 422。
- 图片在 DB、SSE、GraphState 中 **不出现 base64**；仅在 `VisionMessageBuilder` 调模型前读取字节并编码。
- 规则、`app/llm`、翻译、embeddings、rerank 行为不变。

### 1.3 需求决策摘要（brainstorming 定稿）

| 项 | 决策 |
|----|------|
| 多模态 tag | **`MULTIMODAL`**（隐含 Agent 对话能力，**不必**再勾 `CHAT`） |
| Agent 列表过滤 | `tags` 含 **`CHAT` 或 `MULTIMODAL`**（enabled + endpoint + api_key 条件不变） |
| 图片注入范围 | **全图**：Planner + SubAgent + Synthesizer |
| 平时流转 | **`object_key` + `download_url`**（S3 预签名 / Local token URL） |
| 模型边界 | 读存储 → **base64 data URL** → OpenAI 兼容 `content` parts |
| 默认上传限制 | **1 张**；上限由环境变量配置 |
| 默认 MIME | `image/jpeg`, `image/jpg`, `image/png` |
| 存储 | 复用 `resolve_active_storage`；`module_prefix=agent_vision` |
| 存量模型 | **不自动**写入 `MULTIMODAL`；管理员手动勾选 |

### 1.4 非目标（本期）

- 不支持 PDF、视频等多模态类型（仅图片）。
- 不做按 provider 的独立 vision 协议适配层（统一 OpenAI 兼容 parts + data URL）。
- 不实现图片 OCR 替代（用户意图为模型 vision 解析）。
- 不修改 `/model-providers/models` 通用 CRUD 语义。
- 不自动刷新过期 `download_url`（MVP；过期后展示占位或后续迭代刷新接口）。

---

## 2. 标签与选模

### 2.1 常量

`backend/app/sys/model_provider/domain/constants.py` 新增：

```python
MODEL_TAG_MULTIMODAL = "MULTIMODAL"
```

### 2.2 字典

SQL 补丁（idempotent）：各 workspace 的 `MODEL_TAG` 字典插入 code=`MULTIMODAL`、显示名「多模态」。

### 2.3 `list_agent_conversation_models`

在现有 `enabled`、endpoint、api_key 条件上，tag 过滤改为：

```text
tags @> '["CHAT"]' OR tags @> '["MULTIMODAL"]'
```

排序不变：`provider_name ASC`, `model_name ASC`, `id ASC`。

### 2.4 `ChatModelFactory`

允许 tag 校验：`CHAT` **或** `MULTIMODAL` 任一即可构造 chat model。

带 `attachments` 的 run 额外校验：模型 `tags` 须含 **`MULTIMODAL`**，否则 `422 agent.model_vision_not_supported`。

### 2.5 响应扩展

```python
class AgentConversationModelOut(BaseModel):
    # ... 现有字段 ...
    supports_vision: bool  # "MULTIMODAL" in tags
```

前端：仅 `supports_vision=true` 时显示上传按钮。

---

## 3. 环境变量

`backend/app/config.py` 新增（别名遵循现有 `AGENT_*` 惯例）：

| 字段 | 环境变量 | 默认值 | 说明 |
|------|----------|--------|------|
| `agent_vision_image_max_count` | `AGENT_VISION_IMAGE_MAX_COUNT` | `1` | 单次 run 最多附件数 |
| `agent_vision_image_max_bytes` | `AGENT_VISION_IMAGE_MAX_BYTES` | `5242880` | 单张大小上限（5MB） |
| `agent_vision_image_allowed_mime` | `AGENT_VISION_IMAGE_ALLOWED_MIME` | `image/jpeg,image/jpg,image/png` | 逗号分隔 |

**MIME 归一化**（上传校验时）：

- `image/jpg` → `image/jpeg`（IANA 标准；允许客户端上报 `image/jpg` 以免误拒）
- 比较时使用归一化后的值写入存储 `Content-Type`

**扩展名白名单**（与 MIME 双重校验）：`.jpg`、`.jpeg`、`.png`

同步更新 `backend/.env.example` 注释块。

---

## 4. 存储与上传

### 4.1 `WorkspaceFileService`（新增薄门面）

建议路径：`backend/app/files/service/workspace_file_service.py`（或 `app/core/files/`，与现有 `app/s3`、`app/local` 平行）。

职责：

| 方法 | 说明 |
|------|------|
| `upload_file(workspace_id, module_prefix, file_name, payload, content_type)` | `resolve_active_storage` → S3 或 Local |
| `read_object_bytes(workspace_id, object_key)` | 模型边界读字节 |
| `create_download_url(workspace_id, object_key, expires_in)` | 刷新 URL（可选，非 MVP 必需） |

统一返回：

```python
@dataclass
class WorkspaceFileUploadResult:
    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str
```

Object key 规则与 S3 一致：`{module_prefix}/{YYYY}/{MM}/{uuid}.{ext}`。Agent 使用 **`module_prefix=agent_vision`**。

### 4.2 Agent 上传 API

| 项 | 值 |
|----|-----|
| 方法 / 路径 | `POST /workspaces/{workspace_id}/agent/v2/attachments:upload` |
| Router | `backend/app/agent/api/v2/router.py` |
| 权限 | `get_current_user` + `require_workspace_member` |
| Body | `multipart/form-data`，字段 `file` |

校验：

- MIME（归一化后）∈ 配置的 allowed 集合
- 大小 ≤ `agent_vision_image_max_bytes`
- 扩展名 ∈ `.jpg`/`.jpeg`/`.png`

响应 `AgentAttachmentUploadOut`：

```python
class AgentAttachmentUploadOut(BaseModel):
    object_key: str
    file_name: str
    content_type: str | None
    size: int
    download_url: str
```

**响应不含 base64。**

### 4.3 `GET /agent/v2/config` 扩展

```python
class AgentV2ConfigOut(BaseModel):
    memory_backend: str
    vision_image_max_count: int
    vision_image_max_bytes: int
    vision_image_allowed_mime: list[str]
```

---

## 5. Run 协议与持久化

### 5.1 请求体

```python
class AgentAttachmentIn(BaseModel):
    object_key: str = Field(min_length=1)
    file_name: str | None = None
    content_type: str | None = None

class AgentRunCreateV2(BaseModel):
    user_message: str = ""
    attachments: list[AgentAttachmentIn] = Field(default_factory=list)
    # ... 现有字段不变 ...
```

校验（`model_validator` 或服务层）：

1. `len(attachments) ≤ agent_vision_image_max_count`
2. 有 attachments 时模型须含 `MULTIMODAL`
3. 每个 `object_key`：
   - 前缀必须为 `agent_vision/`（防跨模块引用）
   - 对象在工作区存储中存在
   - 再次校验 MIME/大小（读元数据或 HEAD）
4. `user_message` 与 attachments 至少一项非空（保留现有 skill-only 例外逻辑）

### 5.2 用户消息持久化

`agent_message` 用户行：

| 列 | 内容 |
|----|------|
| `content` | 纯文本 `user_message`（兼容标题、记忆提取） |
| `meta_json.attachments` | 见下 |

```json
{
  "attachments": [{
    "object_key": "agent_vision/2026/06/<uuid>.png",
    "file_name": "screenshot.png",
    "content_type": "image/png",
    "size": 12345,
    "download_url": "https://... 或 /workspaces/.../local/files:download?..."
  }]
}
```

- **不**在 `meta_json` 或 `message_json` 存 base64。
- `message_json` 本期可不写；若写也只存 URL 元数据副本，不存 data URL。

### 5.3 会话详情 API

`AgentMessageOut` 扩展（或 attachments 从 `meta_json` 解析暴露）：

```python
class AgentMessageAttachmentOut(BaseModel):
    object_key: str
    file_name: str | None
    content_type: str | None
    size: int | None
    download_url: str | None

class AgentMessageOut(BaseModel):
    # ... 现有字段 ...
    attachments: list[AgentMessageAttachmentOut] = Field(default_factory=list)
```

映射规则：从 `meta_json.attachments` 填充；无则空列表。

---

## 6. 跑图：全链路与模型边界

### 6.1 GraphState

`backend/app/agent/graphs/state.py` 新增：

```python
user_attachments: list[dict]  # URL 元数据，结构与 meta_json.attachments 一致
```

Run 启动时从请求体注入；**不含 base64**。

### 6.2 `VisionMessageBuilder`

建议路径：`backend/app/agent/infrastructure/vision_messages.py`。

```python
class VisionAttachmentCache:
    """Run 级 object_key → base64 data URL 缓存，避免同一 run 多次读存储。"""

def build_vision_human_message(
    text: str,
    attachments: list[dict],
    *,
    workspace_id: uuid.UUID,
    file_service: WorkspaceFileService,
    cache: VisionAttachmentCache,
) -> HumanMessage:
    ...
```

行为：

1. 输入：用户文本 + attachment 元数据（含 `object_key`，**不使用 `download_url` 调模型**）。
2. 对每个 attachment：cache 命中则复用；否则 `read_object_bytes` → `data:{content_type};base64,{...}`。
3. 输出 LangChain `HumanMessage(content=[{"type":"text","text":...}, {"type":"image_url","image_url":{"url":"data:..."}}])`。
4. 无 attachments 时退化为 `HumanMessage(content=text)`。

### 6.3 各节点接入

| 节点 | 改造点 |
|------|--------|
| **Planner** | `planner_messages` 中用户 `HumanMessage` 改用 `build_vision_human_message`；文本仍包「【本轮用户请求】」前缀 |
| **SubAgent** | 扩展 `messages_with_user_input`（或等价函数）：末尾 user 消息带 `state.user_attachments` |
| **Synthesizer** | 合成阶段 user 输入同样带 attachments |
| **chat_history** | `agent_rows_to_langchain`：用户行若 `meta_json.attachments` 非空，重建时走 `VisionMessageBuilder`（需 session/workspace 上下文，经 factory 或 run deps 注入） |

### 6.4 与不同上游模型

- 统一 **OpenAI 兼容** multimodal content parts + **data URL**（不依赖模型访问 Minerva/S3 外网）。
- 沿用 `AgentChatOpenAI`；上游不支持 vision 时映射为 `AppError`（如 `agent.model_vision_rejected`）。
- 本期 **不**引入 provider 级 format 分支。

### 6.5 历史 replay 与模型切换

- 会话历史中某条用户消息含 attachments，后续 run 选用 **非 MULTIMODAL** 模型：`agent_rows_to_langchain` 对该条 **仅保留文本 part**，跳过 image parts（避免文本模型报错）。
- 选用 MULTIMODAL 模型：完整重建 vision message。

---

## 7. 前端（AgentsPage）

### 7.1 能力门控

- `supports_vision` 为 true 时 composer 显示图片上传（Ant Design `Upload`，`beforeUpload` 阻止自动上传）。
- 读取 `GET /agent/v2/config` 的 `vision_image_max_count` 等限制。

### 7.2 上传流程

1. 用户选文件 → `POST .../attachments:upload`。
2. 本地 state 保存 `{ object_key, download_url, file_name, content_type, size }`；预览用 `download_url`。
3. 发送 run 时 body.attachments 传 object_key 等元数据，**不传 base64**。

### 7.3 消息展示

- 用户气泡：文本 + attachments 缩略图（`<img src={download_url} />`）。
- 发送中/失败态与现有 composer 流式逻辑一致。

### 7.4 API 类型

`frontend/src/api/agent.ts` 扩展 `AgentRunCreateBodyV2`、`AgentMessage`、`AgentV2Config` 等。

i18n：`zh-CN` / `en` 上传、超限、MIME 错误文案。

---

## 8. 错误码

| code | HTTP | 场景 |
|------|------|------|
| `agent.model_vision_not_supported` | 422 | 非 MULTIMODAL 模型携带 attachments |
| `agent.vision_attachment_limit` | 422 | 超过 max_count |
| `agent.vision_attachment_invalid` | 422 | object_key 前缀非法或对象不存在 |
| `agent.vision_mime_not_allowed` | 422 | MIME 不在允许列表 |
| `agent.vision_file_too_large` | 422 | 超过 max_bytes |
| `agent.vision_file_required` | 422 | upload 缺少 file |

存储层沿用 `s3.*` / `local.*` / `file_storage.*`。

---

## 9. 架构与目录（建议）

```text
backend/app/files/                          # 新增（或 core/files）
  service/workspace_file_service.py

backend/app/agent/
  infrastructure/vision_messages.py         # VisionMessageBuilder + cache
  api/v2/schemas.py                         # Attachment* schemas
  api/v2/router.py                          # upload + config 扩展
  infrastructure/chat_history.py            # 历史 vision 重建
  infrastructure/chat_model_factory.py      # MULTIMODAL 校验扩展
  graphs/state.py                           # user_attachments
  graphs/nodes/planner.py
  graphs/nodes/synthesizer.py
  infrastructure/chat_history.py            # messages_with_user_input 扩展
  service/agent_graph_run_service.py        # 注入 attachments、cache

backend/app/sys/model_provider/
  domain/constants.py                       # MODEL_TAG_MULTIMODAL
  infrastructure/repository.py              # list 过滤 OR MULTIMODAL

backend/sql/patches/
  2026-06-30-model-tag-multimodal-dict-item.sql

frontend/src/features/agent/
  AgentsPage.tsx                            # 上传 UI
  AgentComposerInput.tsx 或独立 AttachmentBar
frontend/src/api/agent.ts
```

---

## 10. 数据流（总览）

```text
[Upload]  file → WorkspaceFileService → object_key + download_url
[Run]     attachments(object_key*) → GraphState.user_attachments
[Persist] meta_json.attachments (URLs only)
[UI]      img src=download_url
[LLM]     VisionMessageBuilder: read bytes → base64 data URL → HumanMessage
```

---

## 11. 测试要点

- 单元：`VisionMessageBuilder` 无附件 / 单附件 / cache 命中；MIME 归一化 `image/jpg`。
- 集成：upload + run（mock 存储读字节）；非 MULTIMODAL + attachments → 422。
- 集成：`list_agent_conversation_models` 含 CHAT-only 与 MULTIMODAL-only 模型。
- 集成：S3 与 Local 各一条 upload 冒烟（mock gateway）。
- 前端：supports_vision 门控；超限提示。

---

## 12. 实现顺序建议

1. 常量 + 字典补丁 + repository/ChatModelFactory 选模扩展  
2. Settings + config API  
3. WorkspaceFileService + upload API  
4. Run schema + 持久化 + GraphState  
5. VisionMessageBuilder + 全图节点 + chat_history  
6. 前端 composer + 消息展示  
7. 测试与 i18n  

---

## 13. 与既有 Agent CHAT 设计的关系

`2026-06-01-agent-chat-tag-filter-design.md` 规定 Agent 仅 `CHAT`。本期 **扩展** 为：

- 列表与跑图：**`CHAT` 或 `MULTIMODAL`**
- 图片能力：**仅 `MULTIMODAL`**
- 纯文本模型仍可仅勾 `CHAT`；vision 模型建议仅勾 `MULTIMODAL`（不必双勾）

未含二者任一 tag 的模型仍不可用于 Agent。
