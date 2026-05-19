# Volcengine Ark（OpenAI 兼容）LLM 策略实现设计

**日期**：2026-05-17  
**状态**：已实现（2026-05-18 按代码回填）  
**范围**：将 `app.llm` 中火山引擎（Volcengine Ark）策略从占位改为基于 **OpenAI Python SDK（异步）** 的真实对接；重命名策略文件；HTTP 层默认流式输出。

**前置规格**：`docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`

---

## 1. 目标与成功标准

### 1.1 目标

- 删除 `volcengine_placeholder.py`，新增 `volcengine_compatible.py`，实现 `VolcengineCompatibleStrategy`。
- 使用 `AsyncOpenAI` 对接火山 Ark OpenAI 兼容端点（示例：`https://ark.cn-beijing.volces.com/api/v3`）。
- `base_url`、`api_key`、`model` **仍由请求体 / `ChatService` 调用方传入**，不在策略内读取 `ARK_API_KEY` 等环境变量。
- HTTP `POST /workspaces/{workspace_id}/llm/chat/completions`：请求体 **未传** `stream` 时默认为 **`true`**（全 `provider_kind` 适用）。
- 更新策略注册、单元测试与 `docs/ai-api.md` 中占位说明。

### 1.2 成功标准

- `provider_kind=volcengine` 且传入有效 Ark `base_url`、`api_key`、`model` 时，流式与阻塞调用均可返回上游 chunk/completion JSON（`model_dump(mode="json")` 形态）。
- 显式 `"stream": false` 时走 `complete`，行为与 `openai` 一致。
- 占位 501（`ai.provider.not_implemented`）不再出现于 volcengine 路径。
- `pytest backend/tests/test_llm.py` 中 volcengine 相关用例通过。

### 1.3 非目标（本期）

- 从环境变量自动注入 `ARK_API_KEY` 或默认 `base_url`。
- 抽取 `openai` / `volcengine_compatible` 公共基类或共享模块。
- 实现 `aliyun` 占位策略。
- 修改 Agent 模块默认 `provider_kind` 或 `sys_models` 解析逻辑。

---

## 2. 架构变更

### 2.1 文件

| 操作 | 路径 |
|------|------|
| 删除 | `backend/app/llm/strategies/volcengine_placeholder.py` |
| 新增 | `backend/app/llm/strategies/volcengine_compatible.py` |
| 修改 | `backend/app/llm/strategies/__init__.py` |
| 修改 | `backend/app/llm/api/schemas.py` |
| 修改 | `backend/tests/test_llm.py` |
| 修改 | `docs/ai-api.md` |

`ProviderKind.volcengine` 枚举值 **保持不变**。

### 2.2 策略注册

```python
_STRATEGIES = {
    "openai": OpenAICompatibleStrategy(),
    "volcengine": VolcengineCompatibleStrategy(),
    "aliyun": AliyunCompatibleStrategy(),
}
```

`__all__` 导出：`VolcengineCompatibleStrategy` 替换 `VolcenginePlaceholderStrategy`。

---

## 3. `VolcengineCompatibleStrategy` 行为

### 3.1 SDK 与端点

- 客户端：`openai.AsyncOpenAI`（与 `OpenAICompatibleStrategy` 一致，**不使用** 同步 `OpenAI`）。
- `base_url`：调用方传入，规范化 `rstrip("/")`；典型值为 `https://ark.cn-beijing.volces.com/api/v3`。
- `api_key`：调用方传入。
- 调用：`client.chat.completions.create(..., stream=True|False)`。

### 3.2 与 `openai` 的对齐项

本文件内实现（本期不抽取共享模块），逻辑与 `openai_compatible.py`（`ProviderKind.openai` 策略实现）对齐：

- `_completion_kwargs`：`model`、`messages`、`stream`、`temperature`、`max_tokens`、`tools`、`tool_choice`。
- `httpx.Timeout`：来自 `settings.ai_http_connect_timeout` / `ai_http_read_timeout`。
- 错误映射：`_map_openai_error` → `ai.upstream.*` / `ai.error`。
- 日志：请求/响应 JSON 截断、上游 HTTP 错误 WARNING；**不记录** `api_key`。

### 3.3 `complete` / `stream`

- **`complete`**：`stream=False`，`async with AsyncOpenAI(...) as client`，返回 `resp.model_dump(mode="json")`。
- **`stream`**：`stream=True`，`async for chunk in upstream`，逐项 `yield chunk.model_dump(mode="json")`。
- 连接生命周期由 `async with` 管理，避免连接泄漏（对应官方示例中同步 `with completion:` 的语义）。

### 3.4 `ChatService` 与重试

- **不修改** `chat_service.py` 重试逻辑：仅 `complete` 路径重试；流式不重试。
- volcengine 与 openai 在 service 层无差别，仅 `get_strategy(provider_kind)` 解析不同。

---

## 4. HTTP 默认流式

**文件**：`backend/app/llm/api/schemas.py`

```python
stream: bool = True  # 原为 False
```

**路由行为**（`router.py` 不变）：

| `stream` | 响应 |
|----------|------|
| 省略 / `true` | `StreamingResponse` + `stream_sse_lines` |
| `false` | `await chat_service.complete(...)` JSON |

---

## 5. 数据流

```text
Client POST /workspaces/{wid}/llm/chat/completions
  body: provider_kind=volcengine, base_url, api_key, model, [stream 默认 true]
    → ChatCompletionRequest
    → chat_service.stream_sse_lines | complete
    → VolcengineCompatibleStrategy.stream | complete
    → AsyncOpenAI → Ark /api/v3/chat/completions
```

---

## 6. 测试

### 6.1 单元测试（`test_llm.py`）

- 删除：`test_volcengine_placeholder_complete`、`test_volcengine_stream_raises`（501 断言）。
- 新增（mock `app.llm.strategies.volcengine_compatible.AsyncOpenAI`）：
  - `test_volcengine_compatible_complete_success`
  - `test_volcengine_compatible_stream_yields_chunks`
- 保留：`test_get_strategy` 对 volcengine 可解析（若已有或并入 smoke）。

### 6.2 手动联调（可选）

```text
POST /workspaces/{wid}/llm/chat/completions
Authorization: Bearer <token>
{
  "provider_kind": "volcengine",
  "base_url": "https://ark.cn-beijing.volces.com/api/v3",
  "api_key": "<ark-key>",
  "model": "doubao-seed-2-0-lite-260215",
  "user_prompt": "常见的十字花科植物有哪些？"
}
```

省略 `stream` 应返回 `text/event-stream`。

---

## 7. 文档

- `docs/ai-api.md`：将 volcengine 从「占位 501」改为 Ark OpenAI 兼容说明；注明 HTTP `stream` 默认 `true`。
- 本 spec 实现完成后，可在 `2026-04-28-ai-api-openai-compatible-design.md` 的占位章节加注「volcengine 已实现，见 2026-05-17 spec」（可选，非阻塞）。

---

## 8. 实现检查清单（2026-05-18 核对）

- [x] `volcengine_compatible.py` 实现 `VolcengineCompatibleStrategy`
- [x] 删除 `volcengine_placeholder.py`
- [x] `strategies/__init__.py` 注册与导出
- [x] `schemas.py`：`stream: bool = True`
- [x] `test_llm.py` 更新
- [x] `docs/ai-api.md` 更新
- [x] `pytest backend/tests/test_llm.py -q` 通过
