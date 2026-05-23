# LLM 运行时 OpenAI 兼容统一设计

**日期**：2026-05-23  
**状态**：已实现（2026-05-23）  
**范围**：统一 `backend/app/llm` 的运行时模型调用策略；所有模型按 OpenAI Chat Completions 兼容协议对接，不再按供应商类型维护独立策略。外部请求中的 `provider_kind` 旧值保留软兼容，内部业务调用收敛为默认 OpenAI 兼容策略。模型 URL 使用数据库中配置的完整 Chat Completions URL，后端不再拼接或改写路径。同步评估 `backend/app/agent` 影响：Agent 已通过 LangChain `ChatOpenAI` 走 OpenAI 兼容端点，本次不改为走 `app/llm`。

---

## 1. 背景

现有 `app/llm` 仍以 `ProviderKind` 分派策略：

- `openai`：真实 OpenAI 兼容策略。
- `volcengine`：基于 `AsyncOpenAI` 的火山 Ark 兼容策略，逻辑与 `openai` 大量重复。
- `aliyun`：独立占位策略，调用时返回未实现。

实际运行目标已经收敛为同一类协议：调用方提供完整 `base_url`、`api_key`、`model` 与 OpenAI 风格 `messages`，后端通过直接 HTTP 调用访问上游。因此继续按供应商维护策略会增加重复代码、文档分叉和误导性的扩展入口。

---

## 2. 目标与非目标

### 2.1 目标

- `app/llm` 所有运行时调用统一走 `OpenAICompatibleStrategy`。
- 外部 `provider_kind=openai|volcengine|aliyun` 继续可被接收，避免破坏已有 HTTP 调用。
- 内部 `ChatService` 调用接口不再要求业务方传 `provider_kind`。
- 删除 `volcengine_compatible.py`、`aliyun_compatible.py` 及对应 import/export 死代码。
- `base_url` 视为完整请求 URL，后端不再追加 `/chat/completions`，也不再剥离 `/responses` 等路径后缀。
- 明确 `app/agent` 不受 `get_strategy()` 策略分派影响，并补充验证。

### 2.2 非目标

- 不删除 `ProviderKind.volcengine` 与 `ProviderKind.aliyun` 枚举值；它们仅作为兼容输入值存在。
- 不删除 `sys_models.provider_name` 或 `MODEL_PROVIDER` 字典；供应商字段仍用于模型管理页展示、筛选、分组和审计。
- 不把 Agent 改造成走 `app/llm.ChatService`。
- 不移除 `openai` 或 `langchain-openai` 依赖；前者供 `app/llm` 使用，后者供 `app/agent` 使用。
- 不改变数据库结构。

---

## 3. 方案

采用 A+B 组合：

- **A：软兼容统一**。`get_strategy(provider_kind)` 继续接收旧 `provider_kind`，对 `openai`、`volcengine`、`aliyun` 均返回同一个 `OpenAICompatibleStrategy`；未知值仍返回 `ai.provider.unknown`。
- **B：内部接口收敛**。`ChatService.complete()`、`complete_messages()`、`stream_chunks()`、`stream_chunks_messages()`、`stream_sse_lines()` 不再要求调用方传 `provider_kind`。HTTP 层可继续把请求体里的 `provider_kind` 传给兼容入口，但业务模块默认不需要关心供应商类型。

策略注册从“供应商到策略”变为“兼容值到同一策略”：

```python
_OPENAI_COMPATIBLE_STRATEGY = OpenAICompatibleStrategy()

_COMPATIBLE_PROVIDER_KINDS = {"openai", "volcengine", "aliyun"}

def get_strategy(provider_kind: ProviderKind | str = ProviderKind.openai) -> ChatCompletionStrategy:
    """Return the unified OpenAI-compatible strategy for supported legacy provider values."""
```

---

## 4. 组件改动

### 4.1 `backend/app/llm/strategies/openai_compatible.py`

`OpenAICompatibleStrategy` 成为唯一实际执行策略，负责：

- `httpx.AsyncClient` 非流式与流式 HTTP 调用。
- `_completion_kwargs()` 参数构造。
- `_map_openai_error()` 统一错误映射。
- 请求、响应与上游错误日志。
- `base_url` 规范化。

通用 `base_url` 规范化规则：

- 默认做 `rstrip("/")`。
- 不追加 `/chat/completions`。
- 不剥离 `/responses` 或其它路径后缀。
- 不根据 `provider_name` 或 `provider_kind` 判断供应商。

### 4.2 `backend/app/llm/strategies/__init__.py`

清理独立策略导入与导出：

- 删除 `AliyunCompatibleStrategy` import/export。
- 删除 `VolcengineCompatibleStrategy` import/export。
- `_STRATEGIES` 不再实例化多个策略。
- 保留 `get_strategy()` 兼容旧 `provider_kind` 值。

### 4.3 删除文件

删除以下文件：

- `backend/app/llm/strategies/volcengine_compatible.py`
- `backend/app/llm/strategies/aliyun_compatible.py`

删除后，仓库中不应再有对 `VolcengineCompatibleStrategy` 或 `AliyunCompatibleStrategy` 的 import。

### 4.4 `backend/app/llm/domain/models.py`

`ProviderKind` 枚举值暂时保留：

- `openai`
- `volcengine`
- `aliyun`

这些值仅代表兼容输入，不再代表独立供应商运行时策略。后续若要做 API 破坏性清理，可单独立项删除非 `openai` 值。

### 4.5 `backend/app/llm/service/chat_service.py`

内部服务方法默认使用统一策略：

- 移除业务调用必须传 `provider_kind` 的要求。
- HTTP 入口仍可传入 `provider_kind`，由兼容入口解析。
- `translate`、`rule` 等调用方可删除 `ProviderKind.openai` 硬编码参数。

---

## 5. Agent 影响评估

`backend/app/agent` 当前不调用 `app.llm.ChatService` 或 `get_strategy()`。Agent 调用链为：

```text
Agent API(model_id)
  -> AgentGraphRunService
  -> ChatModelFactory
  -> langchain_openai.ChatOpenAI(base_url, api_key, model)
  -> LangGraph nodes / skills / memory extract
```

因此本次 `app/llm` 策略统一不会强制改变 Agent 运行时行为。

本次对 Agent 的处理：

- 不修改 Agent 主调用链。
- 不删除 `langchain-openai` 依赖。
- 不把 `agent_run.provider_kind` 作为本次策略统一的必改项；当前代码写入 `None`，与 `get_strategy()` 无耦合。
- 增加或保留 `ChatModelFactory` 相关验证，确认它仍只依赖 `SysModel.endpoint_url`、`api_key`、`model_name`；当 `endpoint_url` 为完整 `/chat/completions` URL 时，工厂在传给 LangChain 前转换为 API root。
- 文档明确：Agent v2 已是 OpenAI 兼容 endpoint 模式，不受 `provider_kind` 兼容入口分派影响。

---

## 6. 数据流

### 6.1 HTTP 调用

```text
Client
  -> POST /workspaces/{id}/llm/chat/completions
  -> ChatCompletionRequest(provider_kind 可选/兼容)
  -> ChatService
  -> get_strategy(provider_kind)
  -> OpenAICompatibleStrategy
  -> HTTP POST 到配置的完整 URL
```

`provider_kind` 在该路径中只做兼容校验，不影响最终策略选择。

### 6.2 内部业务调用

```text
translate/rule/other service
  -> ChatService.complete 或 stream_sse_lines
  -> OpenAICompatibleStrategy
  -> OpenAI-compatible upstream
```

内部业务调用只需关心模型连接信息，不需要传供应商类型。

---

## 7. 错误处理

- 未知 `provider_kind`：继续返回 `ai.provider.unknown`，HTTP 状态 400。
- 上游鉴权失败、限流、超时、连接失败：继续由 `_map_openai_error()` 映射为 `ai.upstream.*`。
- `provider_kind=aliyun` 不再直接返回 501；若对应 endpoint 不兼容 OpenAI Chat Completions，则以上游错误形式返回。
- 日志继续禁止记录 API Key。

---

## 8. 依赖清理

当前 `backend/pyproject.toml` 未发现火山或阿里云专属 SDK 依赖。保留：

- `httpx`：`app/llm` 统一策略依赖。
- `langchain-openai`：`app/agent` 的 `ChatModelFactory` 依赖。

若实现时发现锁文件、部署脚本或文档中仍声明厂商专属依赖，应同步清理。

---

## 9. 测试

建议覆盖：

- `get_strategy("openai")`、`get_strategy("volcengine")`、`get_strategy("aliyun")` 返回同一个 `OpenAICompatibleStrategy` 实例。
- `get_strategy("unknown")` 返回 `ai.provider.unknown`。
- `OpenAICompatibleStrategy` 对完整 `base_url` 只做尾部斜杠清理。
- `OpenAICompatibleStrategy` 直接请求配置 URL，不拼接 `/chat/completions`，不剥离 `/responses`。
- `ChatService` 在未传 `provider_kind` 时默认走统一策略。
- HTTP 请求仍接受旧 `provider_kind` 值。
- `translate`、`rule` 等内部调用方移除 `ProviderKind.openai` 参数后行为不变。
- `ChatModelFactory` 仍能从 `SysModel` 构造 `ChatOpenAI`，证明 Agent 不依赖 `app/llm` 策略注册。

---

## 10. 文档更新

需要同步更新：

- `docs/ai-api.md`：说明所有 `provider_kind` 兼容值均走 OpenAI 兼容策略；`aliyun` 不再是 501 占位。
- `docs/superpowers/specs/2026-04-28-ai-api-openai-compatible-design.md`：回填原策略模式已收敛为单一 OpenAI 兼容策略。
- `docs/superpowers/specs/2026-05-17-volcengine-compatible-llm-design.md`：标记独立火山策略已被统一策略替代，保留历史说明。
- `docs/agent-module-design.md`：补充 Agent v2 不经 `provider_kind` 策略分派，本次策略统一不改变 Agent 主链路。

---

## 11. 实现检查清单

- [x] 通用策略改为直接请求完整模型 URL，不再拼接或改写路径。
- [x] `get_strategy()` 兼容旧值但返回统一策略。
- [x] `ChatService` 内部接口不再强制要求 `provider_kind`。
- [x] 删除火山与阿里云独立策略文件。
- [x] 清理策略 import/export 与测试引用。
- [x] 移除业务调用方中的 `ProviderKind.openai` 硬编码。
- [x] 更新 LLM 与 Agent 文档。
- [x] 运行后端针对性测试。

---

## 12. 实现对照（以代码为准，2026-05-23）

| 项 | 当前代码位置 |
|----|--------------|
| 统一策略 | `backend/app/llm/strategies/openai_compatible.py` |
| 兼容入口 | `backend/app/llm/strategies/__init__.py` |
| 内部服务默认策略 | `backend/app/llm/service/chat_service.py` |
| HTTP 兼容字段 | `backend/app/llm/api/schemas.py`、`backend/app/llm/api/router.py` |
| Agent 独立链路 | `backend/app/agent/infrastructure/chat_model_factory.py`（兼容完整 `/chat/completions` URL） |
| 回归测试 | `backend/tests/test_llm_strategy_unification.py`、`backend/tests/test_agent_chat_model_factory.py` |

---

## 13. 规格自检（2026-05-23）

| 项 | 结论 |
|----|------|
| 占位符 / TBD | 无未决占位；需要实现的检查项已列入 §11。 |
| 一致性 | 目标、方案、组件改动均以单一 OpenAI 兼容策略为准；`provider_kind` 只保留为兼容输入。 |
| 范围 | 聚焦 `backend/app/llm` 运行时策略与必要文档/测试；Agent 只做影响评估和回归验证，范围可控。 |
| 歧义 | 明确不删除供应商展示字段、不改数据库、不移除 Agent 的 `langchain-openai` 依赖。 |
