# AI 调用模块（`app.llm`）内部说明

面向 **Minerva 服务端内部** 开发者：通过 OpenAI 兼容协议调用上游（含 **LiteLLM** 代理），支持 **阻塞式 JSON** 与 **SSE 流式**。模型连接地址使用数据库中配置的完整 Chat Completions URL，调用策略不再拼接路径。

## 依赖与配置

- Python 依赖：`httpx`（直接向模型配置的完整 URL 发起请求）。
- 环境变量（可选，见 `app.config.Settings`）：
  - `AI_HTTP_CONNECT_TIMEOUT`：连接超时秒数，默认 `10`。
  - `AI_HTTP_READ_TIMEOUT`：读超时秒数，默认 `120`。
  - `AI_RETRY_MAX_ATTEMPTS`：对可重试错误的最大尝试次数，默认 `3`。

可重试错误码（业务码 `AppError.code`）：`ai.upstream.rate_limited`、`ai.upstream.timeout`、`ai.upstream.connection`、`ai.upstream.unavailable`、`ai.upstream.error`。

**流式调用** 当前 **不做** 自动重试（避免半包语义）。

## 模块结构

- `app.llm.domain`：DTO（`ChatMessage`、`ChatCallParams`、`ProviderKind`）。
- `app.llm.strategies`：单一 `OpenAICompatibleStrategy`。`provider_kind=openai|volcengine|aliyun` 仅作为兼容输入值，运行时均走 OpenAI Chat Completions 兼容协议。
- `app.llm.service.chat_service`：`ChatService` 与单例 `chat_service`。
- `app.llm.api.router`：HTTP 表面（需登录且为 workspace 成员）。

## 在代码中调用（推荐）

```python
from app.llm import chat_service

# 阻塞：返回与 OpenAI Chat Completion 对齐的 dict（SDK model_dump）
data = await chat_service.complete(
    base_url="http://127.0.0.1:4000/v1/chat/completions",  # 完整 Chat Completions URL
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
    base_url="http://127.0.0.1:4000/v1/chat/completions",
    api_key="...",
    model="gpt-4o-mini",
    user_prompt="Hi",
):
    ...

# SSE 字节行（data: ...\\n\\n，末尾 data: [DONE]）
async for line in chat_service.stream_sse_lines(
    base_url="http://127.0.0.1:4000/v1/chat/completions",
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
- 请求体（节选）：`provider_kind`、`base_url`、`api_key`、`model`、`system_prompt`、`user_prompt`、`messages[]`、`temperature`、`max_tokens`、`stream`。其中 `base_url` 是完整 Chat Completions URL，不再由后端拼接 `/chat/completions`。
- `stream` **默认 `true`**（省略时走流式）；显式 `stream: false`：响应为 JSON，体为上游 completion 的 JSON 形态。
- `stream: true`（或省略）：`Content-Type: text/event-stream`，每条 `data: <json>`，最后 `data: [DONE]`。

**请勿** 在前端或日志中暴露真实 `api_key`；生产环境建议后续改为仅传 `model_id` 由服务端查 `sys_models`（当前 spec 为可选增强）。

## LiteLLM

将 `base_url` 设为 LiteLLM 提供的完整 OpenAI Chat Completions 地址（通常类似 `/v1/chat/completions`，具体以部署为准），`model` 为 LiteLLM 中配置的模型名，`api_key` 与 LiteLLM/上游要求一致。

## 兼容 provider_kind

HTTP 请求体仍接受 `provider_kind=openai|volcengine|aliyun`，用于兼容历史调用和 OpenAPI 文档。运行时不会按该字段选择不同供应商策略，三者都会进入 `OpenAICompatibleStrategy`。

火山 Ark、阿里云或其它模型服务只要提供 OpenAI Chat Completions 兼容 endpoint，就通过完整 `base_url`、`api_key`、`model` 接入。后端不再改写 `/responses`、`/chat/completions` 等路径；配置什么 URL 就请求什么 URL。

## Agent v2

Agent v2 不调用 `app.llm.ChatService` 或 `/llm/chat/completions`，而是通过 `model_id` 读取 `sys_models` 并由 `ChatModelFactory` 构造 `langchain_openai.ChatOpenAI`。本模块的 `provider_kind` 兼容入口不影响 Agent 主链路。Agent 与 `app.llm` 一致：**直接使用** `sys_models.endpoint_url` 作为上游请求地址，不再剥离或拼接 `/chat/completions` 路径。

## 设计规格

详见 `docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`。
