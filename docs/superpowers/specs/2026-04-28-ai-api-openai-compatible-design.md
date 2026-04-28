# AI 调用模块（OpenAI 兼容 + 策略模式 + LiteLLM）设计说明

**日期**：2026-04-28  
**状态**：已评审待实现  
**范围**：在 `backend/app/ai_api/` 实现以 **OpenAI Chat Completions 请求/响应形态** 为标准的统一调用能力；默认策略使用 **官方 OpenAI Python SDK（异步）** 并通过 `base_url` 对接 **LiteLLM 代理及一切 OpenAI 兼容网关**；**同步（阻塞）与非同步 SSE 流式** 两种数据流并存；火山云、阿里云等非兼容厂商以 **策略占位** 预留；**首期以项目内部服务端调用为主**，不将「对外开放公网集成」作为本期必达项。

---

## 1. 目标与成功标准

### 1.1 目标

- 提供 **内部可复用的领域模型与服务**，使 `rule`、后续任务/编排等模块能以 **统一入参**（`base_url`、`model`、系统提示词、用户提示词、历史对话 `messages`、API Key 及常用生成参数等）调用大模型。
- **入参与出参字段语义**以 OpenAI Chat Completions API 为准（实现阶段可选用 Pydantic 模型对齐官方文档中的子集，避免一次性绑定全部边缘字段）。
- **默认策略 `openai_compatible`**：使用 `AsyncOpenAI` + 可配置 `base_url`，兼容 LiteLLM 及自建 OpenAI 兼容网关。
- **阻塞式**：一次请求返回完整 `chat.completion` 形态结果（或项目内约定的等价 DTO）。
- **流式**：以 **SSE** 向调用方推送增量内容；上游使用 OpenAI SDK 的 `stream=True`（或等价异步流式 API），将 chunk **规范映射** 为与 OpenAI 流式 chunk 一致的 JSON 行事件（`data: {...}\n\n`）。
- **策略模式**：除 `openai_compatible` 外，为 **火山云、阿里云** 等单独策略类 **占位**（接口存在、实现可 `NotImplementedError` 或明确返回「未实现」业务错误），便于后续按厂商文档扩展而不破坏调用方。
- **生产可用**：可配置超时、有限重试（仅针对网络类/429/503 等）、统一错误语义、日志 **不落 API Key**；单元与 API 级测试覆盖主路径与典型失败路径。
- **文档**：FastAPI 若挂载路由则生成 OpenAPI；另提供 **Markdown 使用说明**（面向内部开发者：模块如何 import、如何配置 LiteLLM `base_url`、阻塞与流式调用约定、错误码）。

### 1.2 成功标准

- 在仅替换 `base_url` + `api_key` + `model` 的情况下，可对接 **LiteLLM OpenAI 兼容端**，阻塞与流式均可跑通最小用例。
- 其它 `app/*` 模块仅依赖 `ai_api` 的 **稳定服务接口与 DTO**，不直接依赖具体 SDK 类型泄漏（策略实现细节封装在 `strategies/` 内）。
- 占位策略存在且编译通过，调用时行为明确（未实现即失败可读）。

### 1.3 非目标（本期）

- 面向匿名公网的完整产品化暴露策略（独立 API 网关、复杂配额、多租户对外计费等）—— **不作为本期必达**。
- 火山云、阿里云 **真实** HTTP 对接（仅占位）。
- Embeddings、Images、Assistants 等 **非 Chat Completions** 能力（除非后续单独立项扩展）。

---

## 2. 架构与目录结构

建议目录：

```text
backend/app/ai_api/
  __init__.py
  domain/
    __init__.py
    models.py          # 与 OpenAI 对齐的请求/响应/消息 DTO（子集可迭代扩展）
  strategies/
    __init__.py
    base.py            # 协议/抽象：阻塞 + 流式异步生成器
    openai_compatible.py
    volcengine_placeholder.py
    aliyun_placeholder.py
  service/
    __init__.py
    chat_service.py    # 选策略、超时/重试、观测钩子
  api/                 # 可选：供联调与文档；首期以内部 service 为主
    __init__.py
    router.py
    schemas.py         # 若 HTTP 层需要与 domain 略有不同的视图模型
```

**与 `sys_models` 的关系（可选、后续增强）**：服务层入参可同时支持「调用方显式传入 `base_url` / `api_key`」与「仅传 `model_id` + `workspace_id`，由仓储解析 `sys_models`」。**本期至少实现显式传入**；从表解析可作为实现计划中的后续任务，本 spec 不阻塞核心交付。

---

## 3. 策略模式

### 3.1 策略接口（概念）

每个策略须实现：

- **`complete(...)`**：阻塞式，返回完整 completion 结果（DTO）。
- **`stream(...)`**：异步迭代器，逐项产出与 OpenAI 流式 chunk 对齐的 dict（或由 domain 定义的 `StreamChunk`），由上层封装为 SSE。

策略由 **`provider_kind`**（或枚举）及未来配置决定；**默认** `openai_compatible`。

### 3.2 `openai_compatible`（默认）

- 依赖：`openai` SDK（异步客户端）。
- `base_url` 由调用方传入（LiteLLM 示例：`http://<host>:<port>/v1` 以 SDK 要求为准）。
- 将统一入参映射为 SDK 的 `chat.completions.create`（或异步等价）参数；`messages` 含 system / user / assistant 等角色，与 OpenAI 一致。
- 流式：使用 SDK 流式 API，逐块转换为标准 SSE 事件负载。

### 3.3 占位策略

- `volcengine_placeholder`、`aliyun_placeholder`：类与注册存在，`complete` / `stream` 抛出明确异常或返回业务错误「未实现」，便于调用方与路由层统一处理。

---

## 4. 数据流

### 4.1 阻塞式

```text
调用方 → ChatService.complete → OpenAICompatibleStrategy → 上游 HTTP/SDK
       ← 归一化 ChatCompletion DTO ←
```

### 4.2 SSE 流式

```text
调用方 → ChatService.stream_sse → OpenAICompatibleStrategy (async iter)
       → FastAPI StreamingResponse (media_type text/event-stream)
       → 客户端逐条解析 data: JSON
```

**约定**：SSE 每条事件体为 JSON，结构与 OpenAI 流式 chunk 兼容（至少包含 `choices[].delta` 等调用方解析所需字段）；首版可实现最小可用字段集，并在 Markdown 中写明。

---

## 5. 配置、错误与可观测性

- **超时**：连接超时、读超时可配置（环境变量或 `Settings` 扩展），默认值在实现计划中给出。
- **重试**：仅对超时、连接错误、429、503 等实行有限次指数退避；**不重试** 401/400 等明确业务/鉴权错误。
- **错误模型**：对外（HTTP）与对内（服务异常）统一为项目既有异常体系或 `ai_api` 内轻量错误类型，**不向上游原文泄露密钥**。
- **日志**：记录 `model`、`base_url` 主机（可脱敏路径）、耗时、错误类型；**禁止**记录 `api_key` 或完整 Authorization。

---

## 6. HTTP 层（内部优先）

- 路由可挂载在现有 `app/api/router.py` 下前缀（例如 `/ai/...`），**鉴权与权限与项目内部 API 一致**（若当前内部接口无统一鉴权，则与实现计划同步选用最小约束）。
- **首期消费者仍为 Python 模块**；HTTP 主要用于联调、自动化测试与 OpenAPI 文档，**不承诺**对外第三方集成场景。

---

## 7. 依赖

- 在 `backend/pyproject.toml` 增加 `openai`（版本在实现计划中锁定，建议使用与 Python 3.11+ 兼容的当前稳定主版本）。
- 保留 `httpx` 作为已有依赖；**仅在**需要 SDK 无法覆盖的兜底场景再引入原始 HTTP 调用（本 spec 不强制）。

---

## 8. 测试

- **单元测试**：`openai_compatible` 对上游使用 mock（`respx` 或 mock SDK），覆盖：成功 completion、流式若干 chunk、401、429、超时。
- **API 测试**（若启用路由）：`TestClient` 验证阻塞 JSON 与流式 SSE 头及至少一行事件。
- **占位策略**：断言调用即得到明确未实现行为。

---

## 9. 文档交付

- **`docs/ai-api.md`**（或 `docs/superpowers/` 下由项目惯例指定的路径）：内部开发者指南——模块结构、阻塞/流式示例代码片段、LiteLLM `base_url` 配置说明、环境变量、错误与重试语义。
- **OpenAPI**：随 FastAPI 路由自动生成；说明中标注「内部使用为主」。

---

## 10. 规格自检（2026-04-28）

| 项 | 结论 |
|----|------|
| 占位符 / TBD | 无未决 TBD；`sys_models` 解析为可选增强，已写明优先级。 |
| 一致性 | 默认策略与 LiteLLM/OpenAI 兼容前提一致；流式与阻塞均经同一策略接口。 |
| 范围 | 单模块 + 可选 HTTP + 文档，适合一份实现计划；厂商真实对接拆到后续 spec。 |
| 歧义 | 「内部使用为主」已明确：不将公网对外开放作为本期目标；HTTP 仍可存在用于联调。 |

---

## 11. 后续工作入口

实现计划获批后，使用 **`writing-plans`** 产出分步实现清单（依赖安装、目录脚手架、`openai_compatible` 实现、SSE、`ChatService`、路由、测试、`docs/ai-api.md`）。**不在本 spec 中写具体代码。**
