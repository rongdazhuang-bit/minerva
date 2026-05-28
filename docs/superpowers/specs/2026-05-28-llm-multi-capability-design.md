# LLM 多能力入参/出参统一与 model_id 中心化设计

**日期**：2026-05-28  
**状态**：待实现  
**范围**：扩展 `backend/app/llm`，以「模型类型」策略封装文本（Chat Completions）、Embedding、Rerank 三类能力的入参/出参实体；翻译（translate）与文本共用 Chat 策略；对外 HTTP 按能力分路由；调用方统一传 `model_id`，服务端从 `sys_models` 解析凭证与 `endpoint_url`（完整 URL，不做路径拼接）；彻底移除 `base_url`/`api_key`/`model` 显式传参。

---

## 1. 背景

当前 `app/llm` 仅支持 OpenAI Chat Completions：

- 入参为 `ChatCallParams`（含 `base_url`、`api_key`、`model`），出参为无类型 `dict[str, Any]`。
- 策略分派按 `provider_kind`（openai/volcengine/aliyun），三种值实际走同一 `OpenAICompatibleStrategy`。
- Embedding、Rerank 未实现；翻译在业务层（`translate_llm.py`）自行解析 `sys_models` 后调用 `chat_service.complete`。
- 各业务模块各自解析 OpenAI 响应（如 `_openai_completion_text`）。

目标：在统一模块内支持多模型类型，封装入参/出参实体，并以 `model_type` 选择策略；HTTP 与内部调用均改为 `model_id` 模式。

---

## 2. 目标与非目标

### 2.1 目标

- 三种运行时策略：`TextChatStrategy`（text + translate）、`EmbeddingStrategy`、`RerankStrategy`。
- 各能力具备独立 Pydantic 入参/出参实体；策略负责构造上游请求体与解析响应。
- 新增 `LlmService` 门面 + `ModelResolver`（`model_id` → `ResolvedModel`）。
- HTTP：`POST /chat/completions`、`POST /embeddings`、`POST /rerank`；各端点强校验 `model_type`。
- 彻底迁移现有调用方（rule 润色、translate）；删除 `ChatService` 及 HTTP 中的 `base_url`/`api_key`/`model`/`provider_kind`。
- 上游 URL 直接使用 `sys_models.endpoint_url`（完整 URL，仅 `rstrip("/")`）。

### 2.2 非目标

- 不改造 `app/agent`（继续 LangChain 独立路径）。
- 不实现 `load_balancing_enabled` 负载均衡。
- 不修改 `sys_models` 表结构。
- 不在本期实现 Agent 走 `app/llm`。
- 不移除 `ProviderKind` 枚举的历史存在（若 domain 仍引用可保留），但不再参与 HTTP 或运行时路由。

---

## 3. 方案选型

曾评估三种方案：

| 方案 | 描述 | 结论 |
|------|------|------|
| **A（采用）** | 统一 `LlmService` + 按能力分策略 + 实体 DTO | 边界清晰，符合目标 |
| B | 多 Service 并列（Chat/Embedding/Rerank） | 模型解析与重试逻辑重复 |
| C | 单一 `invoke(model_id, payload: dict)` | 类型弱，与分路由目标冲突 |

**策略划分（translate 与 text 共用 Chat）**：

- `text`、`translate` → `TextChatStrategy`；translate 仅在 service/resolver 层限制 `allowed_types`。
- `embedding` → `EmbeddingStrategy`。
- `rerank` → `RerankStrategy`。

---

## 4. 架构

```text
HTTP / 业务模块（rule、translate、未来 RAG）
    ↓ model_id + 能力入参实体 + AsyncSession
LlmService（模型解析、类型校验、重试、SSE 封装）
    ↓ ResolvedModel + CallParams
策略层（TextChat | Embedding | Rerank）
    ↓ httpx POST endpoint_url
出参实体（TextChatResult | EmbeddingResult | RerankResult）
```

### 4.1 目录结构

```text
app/llm/
├── domain/
│   ├── models.py          # ModelType 常量、各能力 CallParams / Result
│   └── resolved_model.py  # ResolvedModel
├── strategies/
│   ├── http_common.py     # 共用 httpx、错误映射、日志
│   ├── base.py            # 策略 Protocol
│   ├── text_chat.py       # text + translate
│   ├── embedding.py
│   ├── rerank.py
│   └── __init__.py        # get_*_strategy()
├── service/
│   ├── model_resolver.py
│   └── llm_service.py     # llm_service 单例
└── api/
    ├── schemas.py
    └── router.py
```

迁移完成后删除 `service/chat_service.py`；`strategies/openai_compatible.py` 逻辑并入 `text_chat.py` 与 `http_common.py`。

---

## 5. Domain 实体

### 5.1 ResolvedModel

从 `sys_models` 解析，供策略层使用：

| 字段 | 来源 |
|------|------|
| `model_id` | `sys_models.id` |
| `model_name` | `sys_models.model_name`（上游 `model` 字段） |
| `model_type` | `sys_models.model_type` |
| `endpoint_url` | `sys_models.endpoint_url`（完整 URL） |
| `api_key` | `sys_models.api_key` |

### 5.2 model_type 与端点映射

| `MODEL_TYPE` code | 策略 | 允许 HTTP 端点 |
|-------------------|------|----------------|
| `text` | TextChat | `/llm/chat/completions` |
| `translate` | TextChat | `/llm/chat/completions` |
| `embedding` | Embedding | `/llm/embeddings` |
| `rerank` | Rerank | `/llm/rerank` |

不匹配 → `AppError("ai.model_type_mismatch", ..., 422)`。

### 5.3 TextChatCallParams / TextChatResult

**入参**（对齐 OpenAI Chat Completions）：

- `messages: list[dict[str, Any]]`
- `temperature`, `max_tokens`, `top_p`, `n`, `stop`
- `presence_penalty`, `frequency_penalty`
- `stream: bool = False`
- `tools`, `tool_choice`（可选，保持现有 tool calling 能力）

**出参**：

- 结构化字段：`id`, `model`, `usage`, `choices`
- `raw: dict[str, Any]` 保留原始 JSON
- `assistant_text() -> str` 提取 assistant 文本

### 5.4 EmbeddingCallParams / EmbeddingResult

**入参**：

- `input: str | list[str]`
- `dimensions: int | None`
- `encoding_format: str = "float"`

**出参**：

- `data: list[dict]`（含 `index`, `embedding`）
- `model`, `usage`, `raw`

### 5.5 RerankCallParams / RerankResult

**入参**：

- `query: str`
- `documents: list[str]`（至少 1 条）
- `top_n: int | None`

**出参**：

- `id: str | None`
- `results: list[dict]`（含 `index`, `relevance_score`）
- `raw`

---

## 6. 策略层

### 6.1 公共 HTTP（`http_common.py`）

自现有 `openai_compatible.py` 抽取：

- `normalize_endpoint_url(url)` — 仅 `rstrip("/")`
- 请求头、`httpx.Timeout`、上游错误 → `AppError`（沿用 `ai.upstream.*`）
- 日志截断（请求/响应 JSON）

### 6.2 各策略职责

| 策略 | 方法 | 上游 body 要点 | 流式 |
|------|------|----------------|------|
| TextChat | `complete` / `stream` | `model`, `messages`, 采样参数, `stream` | stream 支持 SSE |
| Embedding | `embed` | `model`, `input`, `dimensions`, `encoding_format` | 否 |
| Rerank | `rerank` | `model`, `query`, `documents`, `top_n` | 否 |

三种策略均：`POST resolved.endpoint_url`，`Authorization: Bearer {api_key}`。

### 6.3 策略注册

```python
_CHAT_MODEL_TYPES = frozenset({"text", "translate"})
_EMBEDDING_MODEL_TYPES = frozenset({"embedding"})
_RERANK_MODEL_TYPES = frozenset({"rerank"})
```

移除按 `provider_kind` 分派的 `get_strategy()`。

---

## 7. Service 层

### 7.1 ModelResolver

```python
async def resolve_model(
    session: AsyncSession,
    *,
    workspace_id: UUID,
    model_id: UUID,
    allowed_types: frozenset[str],
) -> ResolvedModel
```

校验：

1. 行存在且 `workspace_id` 匹配 → 否则 `ai.model_not_found`（404）
2. `enabled` → 否则 `ai.model_disabled`（422）
3. `model_type in allowed_types` → 否则 `ai.model_type_mismatch`（422）
4. `endpoint_url`、`api_key` 非空 → 否则 `ai.model_misconfigured`（422）

### 7.2 LlmService

| 方法 | allowed_types | 重试 |
|------|---------------|------|
| `complete_chat` | text, translate | ✅ 指数退避（沿用现有 `_RETRIABLE_CODES`） |
| `stream_chat` / `stream_sse_lines` | text, translate | ❌ |
| `embed` | embedding | ✅ |
| `rerank` | rerank | ✅ |

保留 `build_openai_messages(system_prompt, user_prompt, messages)` 供 HTTP 与 rule 润色使用。

单例：`llm_service`。

---

## 8. HTTP API

前缀：`/workspaces/{workspace_id}/llm`（与现有一致）。

### 8.1 POST /chat/completions

**请求体**：

- `model_id: UUID`（必填）
- `system_prompt`, `user_prompt`, `messages`
- `temperature`, `max_tokens`, `top_p`, `n`, `stop`, `presence_penalty`, `frequency_penalty`
- `stream: bool = True`

**响应**：阻塞 → `TextChatResult`；流式 → SSE（格式不变）。

**allowed_types**：`{"text", "translate"}`。

### 8.2 POST /embeddings

**请求体**：`model_id`, `input`, `dimensions`, `encoding_format`。

**响应**：`EmbeddingResult`。**allowed_types**：`{"embedding"}`。

### 8.3 POST /rerank

**请求体**：`model_id`, `query`, `documents`, `top_n`。

**响应**：`RerankResult`。**allowed_types**：`{"rerank"}`。

### 8.4 移除字段

自 Chat HTTP 请求体移除：`provider_kind`, `base_url`, `api_key`, `model`。

---

## 9. 现有调用方迁移

| 模块 | 变更 |
|------|------|
| `rule_base_service.py` | `llm_service.complete_chat(session, workspace_id, model_id, ...)`；使用 `result.assistant_text()` |
| `translate_llm.py` | 调用 `llm_service.complete_chat`，`allowed_types={"translate"}`；删除本地 endpoint 解析与 `_openai_completion_text` |
| `tests/test_llm_strategy_unification.py` | 重写为三类策略 + resolver 测试 |

---

## 10. 错误码

| 场景 | code | HTTP |
|------|------|------|
| 模型不存在 | `ai.model_not_found` | 404 |
| 模型未启用 | `ai.model_disabled` | 422 |
| model_type 与端点不匹配 | `ai.model_type_mismatch` | 422 |
| 缺少 endpoint/api_key | `ai.model_misconfigured` | 422 |
| 上游错误 | `ai.upstream.*` | 沿用现有 |

---

## 11. 测试计划

1. 策略单元测试：request 构造、response 解析（mock httpx）。
2. ModelResolver：enabled、type、misconfigured 分支。
3. HTTP 集成：三端点 happy path；错误 model_type → 422。
4. 回归：rule 润色、translate 段落翻译。

---

## 12. 文档

- 本 spec：`docs/superpowers/specs/2026-05-28-llm-multi-capability-design.md`
- 实现后更新：`docs/ai-api.md`

---

## 13. 参考

- `docs/superpowers/specs/2026-05-23-llm-openai-compatible-runtime-unification-design.md`（httpx 直连、完整 URL）
- `docs/superpowers/specs/2026-05-20-document-translate-design.md`（translate 业务）
- `docs/superpowers/specs/2026-04-25-model-providers-management-design.md`（`sys_models` + `MODEL_TYPE` 字典）
