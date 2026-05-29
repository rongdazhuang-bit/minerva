# AI 调用模块（`app.llm`）内部说明

面向 **Minerva 服务端内部** 开发者：通过 OpenAI 兼容协议调用上游，支持 **Chat Completions**、**Embeddings**、**Rerank** 三类能力；调用方统一传 `model_id`，服务端从 `sys_models` 解析 `endpoint_url`（完整 URL，不拼接路径）、`api_key` 与 `model_name`。

## 依赖与配置

- Python 依赖：`httpx`（直接向模型配置的完整 URL 发起请求）。
- 环境变量（可选，见 `app.config.Settings`）：
  - `AI_HTTP_CONNECT_TIMEOUT`：连接超时秒数，默认 `10`。
  - `AI_HTTP_READ_TIMEOUT`：读超时秒数，默认 `120`。
  - `AI_RETRY_MAX_ATTEMPTS`：对可重试错误的最大尝试次数，默认 `3`。

可重试错误码（业务码 `AppError.code`）：`ai.upstream.rate_limited`、`ai.upstream.timeout`、`ai.upstream.connection`、`ai.upstream.unavailable`、`ai.upstream.error`。

**流式调用**（仅 Chat）当前 **不做** 自动重试（避免半包语义）。

## 模块结构

- `app.llm.domain`：`ChatMessage`、`TextChatCallParams`/`TextChatResult`、`EmbeddingCallParams`/`EmbeddingResult`、`RerankCallParams`/`RerankResult`、`ResolvedModel`。
- `app.llm.strategies`：`TextChatStrategy`（text + translate）、`EmbeddingStrategy`、`RerankStrategy`；共用 `http_common.py`。
- `app.llm.service.model_resolver`：`model_id` → `ResolvedModel`（校验 enabled、tags、endpoint/api_key）。
- `app.llm.service.llm_service`：`LlmService` 与单例 `llm_service`。
- `app.llm.api.router`：HTTP 代理（需登录且为 workspace 成员）。

## MODEL_TAG 与端点

| tag code | 策略 | HTTP 端点 |
|----------|------|-----------|
| `TEXT`, `TRANSLATE` | TextChat | `POST .../llm/chat/completions` |
| `EMBEDDINGS` | Embedding | `POST .../llm/embeddings` |
| `RERANKING` | Rerank | `POST .../llm/rerank` |

不匹配 → `ai.model_tag_mismatch`（422）。规则润色等场景可传 `excluded_tags`（例如排除 `TRANSLATE`）。

## 在代码中调用（推荐）

```python
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession

from app.llm import ChatMessage, EmbeddingCallParams, llm_service

# Chat（TEXT 或 TRANSLATE，通过 allowed_tags 约束）
result = await llm_service.complete_chat(
    session,
    workspace_id=workspace_id,
    model_id=model_id,
    system_prompt="You are helpful.",
    user_prompt="Hello",
    messages=[],
    temperature=0.2,
    max_tokens=256,
    allowed_tags=frozenset({"TEXT"}),  # translate 模块传 frozenset({"TRANSLATE"})
)
text = result.assistant_text()

# Embedding
emb = await llm_service.embed(
    session,
    workspace_id=workspace_id,
    model_id=embedding_model_id,
    params=EmbeddingCallParams(input="hello world", dimensions=1536),
)

# Rerank
from app.llm.domain.models import RerankCallParams

ranked = await llm_service.rerank(
    session,
    workspace_id=workspace_id,
    model_id=rerank_model_id,
    params=RerankCallParams(query="q", documents=["a", "b"], top_n=2),
)

# Chat 流式 SSE 字节行
async for line in llm_service.stream_sse_lines(
    session,
    workspace_id=workspace_id,
    model_id=model_id,
    user_prompt="Hi",
):
    ...
```

消息拼装顺序：`system_prompt`（若有）→ `messages` 历史 → `user_prompt`（若有，作为最后一条 user）。

## HTTP（联调 / OpenAPI）

均需：`Authorization: Bearer <access_token>`，且用户须为该 workspace 成员。

### `POST /workspaces/{workspace_id}/llm/chat/completions`

- 请求体：`model_id`、`system_prompt`、`user_prompt`、`messages[]`、`temperature`、`max_tokens`、`top_p`、`n`、`stop`、`presence_penalty`、`frequency_penalty`、`stream`（默认 `true`）。
- `stream: false`：JSON 响应（`TextChatResult` 形态）。
- `stream: true`：`text/event-stream`，`data: <json>`，末尾 `data: [DONE]`。

### `POST /workspaces/{workspace_id}/llm/embeddings`

- 请求体：`model_id`、`input`（字符串或数组）、`dimensions`、`encoding_format`（默认 `float`）。

### `POST /workspaces/{workspace_id}/llm/rerank`

- 请求体：`model_id`、`query`、`documents[]`、`top_n`。

**请勿** 在客户端传 `api_key`；凭证由服务端从 `sys_models` 读取。

## 模型解析错误码

| code | 说明 |
|------|------|
| `ai.model_not_found` | 模型不存在或不属于 workspace |
| `ai.model_disabled` | 模型未启用 |
| `ai.model_tag_mismatch` | tags 与端点/allowed_tags 不匹配 |
| `ai.model_misconfigured` | 缺少 endpoint_url 或 api_key |

## Agent v2

Agent v2 不调用 `app.llm.LlmService`，而是通过 `model_id` 读取 `sys_models` 并由 `ChatModelFactory` 构造 `langchain_openai.ChatOpenAI`；Agent 独立校验 `tags` 含 `TEXT`。Agent 与 `app.llm` 一致：**直接使用** `sys_models.endpoint_url` 作为上游请求地址。

## 设计规格

- `docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`
- `docs/superpowers/specs/2026-05-23-llm-openai-compatible-runtime-unification-design.md`
