# AI 调用模块（`app.llm`）内部说明

面向 **Minerva 服务端内部** 开发者：通过 OpenAI 兼容协议调用上游（含 **LiteLLM** 代理），支持 **阻塞式 JSON** 与 **SSE 流式**。

## 依赖与配置

- Python 依赖：`openai`（异步客户端）、`httpx`（由 SDK 使用）。
- 环境变量（可选，见 `app.config.Settings`）：
  - `AI_HTTP_CONNECT_TIMEOUT`：连接超时秒数，默认 `10`。
  - `AI_HTTP_READ_TIMEOUT`：读超时秒数，默认 `120`。
  - `AI_RETRY_MAX_ATTEMPTS`：对可重试错误的最大尝试次数，默认 `3`。

可重试错误码（业务码 `AppError.code`）：`ai.upstream.rate_limited`、`ai.upstream.timeout`、`ai.upstream.connection`、`ai.upstream.unavailable`、`ai.upstream.error`。

**流式调用** 当前 **不做** 自动重试（避免半包语义）。

## 模块结构

- `app.llm.domain`：DTO（`ChatMessage`、`ChatCallParams`、`ProviderKind`）。
- `app.llm.strategies`：`openai_compatible`（默认）、`volcengine` / `aliyun` 占位。
- `app.llm.service.chat_service`：`ChatService` 与单例 `chat_service`。
- `app.llm.api.router`：HTTP 表面（需登录且为 workspace 成员）。

## 在代码中调用（推荐）

```python
from app.llm import ProviderKind, chat_service

# 阻塞：返回与 OpenAI Chat Completion 对齐的 dict（SDK model_dump）
data = await chat_service.complete(
    provider_kind=ProviderKind.openai_compatible,
    base_url="http://127.0.0.1:4000/v1",  # LiteLLM OpenAI 兼容根路径
    api_key="...",
    model="gpt-4o-mini",
    system_prompt="You are helpful.",
    user_prompt="Hello",
    messages=[],  # 可选历史：ChatMessage 列表
    temperature=0.2,
    max_tokens=256,
)

# 流式：异步迭代 OpenAI 流 chunk dict
async for chunk in chat_service.stream_chunks(
    provider_kind=ProviderKind.openai_compatible,
    base_url="http://127.0.0.1:4000/v1",
    api_key="...",
    model="gpt-4o-mini",
    user_prompt="Hi",
):
    ...

# SSE 字节行（data: ...\\n\\n，末尾 data: [DONE]）
async for line in chat_service.stream_sse_lines(
    provider_kind=ProviderKind.openai_compatible,
    base_url="http://127.0.0.1:4000/v1",
    api_key="...",
    model="gpt-4o-mini",
    user_prompt="Hi",
):
    # line: bytes
    ...
```

消息拼装顺序：`system_prompt`（若有）→ `messages` 历史 → `user_prompt`（若有，作为最后一条 user）。

## HTTP（联调 / OpenAPI）

- `POST /workspaces/{workspace_id}/llm/chat/completions`
- 鉴权：`Authorization: Bearer <access_token>`，且用户须为该 workspace 成员。
- 请求体（节选）：`provider_kind`、`base_url`、`api_key`、`model`、`system_prompt`、`user_prompt`、`messages[]`、`temperature`、`max_tokens`、`stream`。
- `stream: false`：响应为 JSON，体为上游 completion 的 JSON 形态。
- `stream: true`：`Content-Type: text/event-stream`，每条 `data: <json>`，最后 `data: [DONE]`。

**请勿** 在前端或日志中暴露真实 `api_key`；生产环境建议后续改为仅传 `model_id` 由服务端查 `sys_models`（当前 spec 为可选增强）。

## LiteLLM

将 `base_url` 设为 LiteLLM 提供的 OpenAI 兼容地址（通常以 `/v1` 结尾，具体以部署为准），`model` 为 LiteLLM 中配置的模型名，`api_key` 与 LiteLLM/上游要求一致。

## 占位策略

`provider_kind` 为 `volcengine` 或 `aliyun` 时返回 HTTP 501，业务码 `ai.provider.not_implemented`。

## 设计规格

详见 `docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`。
