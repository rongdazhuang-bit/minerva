# 后端日志框架设计

**日期**：2026-05-23  
**状态**：已实现（2026-05-23）  
**范围**：为后端运行进程设计统一日志框架，覆盖 FastAPI API、Celery Worker、Celery Beat。日志以 JSON 行格式同时输出到 stdout 与本地滚动文件，按标准级别划分，文件按天滚动并保留 7 天。API 请求与响应报文需要进入日志，但必须经过统一脱敏与大小截断。整体设计保留现有 `logging.getLogger(__name__)` 使用方式，并为关键业务边界补充结构化日志，方便排查问题。

---

## 1. 背景

当前后端已经在部分模块中零散使用 Python 标准库 `logging`，例如 LLM 上游调用、Celery demo 任务、Agent run、OCR 扫描和文档翻译 pipeline。现状问题是：

- 没有集中日志初始化入口。
- 没有统一 JSON 格式。
- 没有本地日志文件滚动与 7 天保留策略。
- API 请求/响应报文没有统一记录。
- HTTP 请求、Celery 任务和业务 run 之间缺少统一关联 ID。
- 异常、外部依赖、长流程任务的关键字段不够一致。

仓库已有设计文档强调 AI API、Agent、OCR 等场景不得泄露 `api_key`、Authorization、大 Base64、文件内容等敏感或超大数据。因此本次日志框架必须把脱敏、截断和上下文关联作为基础能力，而不是由各业务模块临时实现。

---

## 2. 目标与非目标

### 2.1 目标

- 后端 API、Celery Worker、Celery Beat 使用同一套日志初始化和 JSON Formatter。
- 日志级别支持标准等级：`DEBUG`、`INFO`、`WARNING`、`ERROR`、`CRITICAL`。
- 日志同时输出到 stdout 和本地文件。
- 本地日志文件按进程拆分：`api.log`、`worker.log`、`beat.log`。
- 本地日志文件按天滚动，保留 7 天。
- API 访问日志记录请求报文与响应报文，并统一脱敏、截断。
- 每个 HTTP 请求生成或复用 `X-Request-ID`，并在 API 日志、异常日志和后续 Celery 任务日志中贯穿。
- 保留现有 `logging.getLogger(__name__)` 使用方式，减少业务代码迁移成本。
- 为核心边界补充关键日志：API、异常、Celery、外部依赖、Agent、OCR、翻译、调度。
- 新增环境变量时同步 `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev`。

### 2.2 非目标

- 不引入 `structlog`、`loguru` 等第三方日志框架。
- 不设计前端浏览器端文件日志。
- 不替代数据库中的业务审计日志，例如 `ocr_file_log`、`agent_run`、`agent_run_node`。
- 不在首轮为每个 CRUD service 增加细粒度 debug 日志。
- 不记录未脱敏凭证、完整文件内容、大 Base64、完整 OCR 原文或无限长 LLM 报文。
- 不改变数据库结构。

---

## 3. 方案选择

采用方案 A：Python 标准库 `logging` + 自定义 JSON Formatter + 中间件/Filter。

保留现有模块级 logger：

```python
logger = logging.getLogger(__name__)
```

新增集中基础设施模块，例如 `backend/app/logging_config.py`，统一负责：

- root logger、`uvicorn`、`celery`、业务 logger 的 handler 与 level。
- JSON 行格式输出。
- stdout handler。
- 按进程选择文件 handler。
- `TimedRotatingFileHandler` 日滚动与 7 天保留。
- 敏感字段脱敏。
- 超长 body 截断。
- `request_id` 等上下文字段注入。

该方案与现有代码最兼容，不需要业务模块改用新的 logger API。业务日志如需补充结构化字段，可继续使用 `extra={...}`。

---

## 4. 配置设计

在 `backend/app/config.py` 新增日志相关 Settings，并同步 `.env.example` 与 `.env.dev`。

配置项如下：

| 配置项 | 默认值 | 说明 |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | 应用日志级别，支持标准等级。 |
| `LOG_DIR` | `backend/logs` | 本地日志目录。 |
| `LOG_RETENTION_DAYS` | `7` | 日志文件保留天数。 |
| `LOG_BODY_ENABLED` | `true` | 是否记录 API 请求/响应报文。 |
| `LOG_BODY_MAX_CHARS` | `20000` | 单个请求或响应 body 写入日志前的最大字符数。 |
| `LOG_FILE_ENABLED` | `true` | 是否写入本地滚动文件。 |
| `LOG_STDOUT_ENABLED` | `true` | 是否输出到 stdout。 |

实现时应保证：

- `LOG_LEVEL` 解析大小写不敏感，非法值回退或启动时报稳定配置错误。
- `LOG_DIR` 支持相对路径和绝对路径；相对路径以 `backend/` 为基准。
- `LOG_RETENTION_DAYS` 默认固定为 7，满足当前需求。
- `backend/logs/` 加入 `.gitignore`。

---

## 5. 初始化设计

### 5.1 FastAPI API

在 `backend/app/main.py` 创建 `FastAPI` app 前初始化日志：

```python
configure_logging(process_type="api")
```

API 进程输出：

- stdout：JSON 行。
- 文件：`backend/logs/api.log`。

### 5.2 Celery Worker 与 Beat

在 `backend/app/celery_app.py` 构建 Celery app 时初始化日志：

```python
configure_logging(process_type=resolve_celery_process_type())
```

`resolve_celery_process_type()` 根据进程参数或 Celery 信号区分：

- Worker 写入 `backend/logs/worker.log`。
- Beat 写入 `backend/logs/beat.log`。

Celery 当前已设置 `worker_hijack_root_logger=False`，该策略应保持，避免 Celery 接管 root logger 后隐藏业务模块日志。

对于 worker 子进程或线程池场景，使用 Celery signal 确保日志配置幂等初始化。`configure_logging()` 必须可重复调用，不重复添加 handler。

---

## 6. JSON 日志结构

每一行日志是一条 JSON object。基础字段：

| 字段 | 说明 |
| --- | --- |
| `timestamp` | ISO 8601 时间，带时区或 UTC 标识。 |
| `level` | 标准日志级别。 |
| `logger` | logger 名称。 |
| `message` | 格式化后的日志消息。 |
| `event` | 事件名，例如 `http.request`、`celery.task.started`。 |
| `process_type` | `api`、`worker`、`beat`。 |
| `process_id` | OS 进程 ID。 |
| `thread_name` | 线程名。 |
| `module` | Python 模块。 |
| `line` | 源码行号。 |
| `request_id` | HTTP/Celery 贯穿 ID。 |
| `task_id` | Celery task id。 |
| `run_id` | Agent 或业务长流程 run id。 |
| `exception` | 异常类型、消息、栈信息摘要。 |

业务代码通过 `extra` 传入的字段会合并到 JSON 输出中，但应避免覆盖基础字段。Formatter 需要处理不可 JSON 序列化对象，无法序列化时转成字符串摘要。

---

## 7. API 请求与响应报文日志

新增 HTTP 日志中间件，覆盖所有 API 请求。中间件职责：

- 读取或生成 `X-Request-ID`。
- 将 `request_id` 写入 `contextvars`。
- 在响应头返回同一个 `X-Request-ID`。
- 记录请求元数据与请求报文。
- 记录响应元数据与响应报文。
- 记录耗时。
- 捕获中间件层可见异常并写入错误日志。

### 7.1 请求日志

请求日志事件名：`http.request`。

字段包括：

- `request_id`
- `method`
- `path`
- `query`
- `client_ip`
- `headers` 摘要
- `content_type`
- `request_body`

请求体记录策略：

- JSON、form、普通文本尽量记录。
- `multipart/form-data`、文件上传、二进制内容只记录字段名、文件名、content-type、大小摘要，不记录文件内容。
- 读取请求 body 后必须重建 ASGI receive，保证后续 FastAPI/Pydantic 正常解析。
- query、headers、body 全部进入脱敏流程。

### 7.2 响应日志

响应日志事件名：`http.response`。

字段包括：

- `request_id`
- `method`
- `path`
- `status_code`
- `duration_ms`
- `content_type`
- `response_body`

响应体记录策略：

- 普通 JSON 响应记录脱敏、截断后的 body。
- `StreamingResponse`、SSE、文件下载、大二进制响应不消费完整流，只记录 `streaming=true`、content-type、状态码、可能的大小摘要。
- 对超过 `LOG_BODY_MAX_CHARS` 的 body 截断，并记录原始长度。

### 7.3 异常日志

异常日志事件名：`http.error`。

在 `backend/app/errors.py` 中补充：

- `AppError` handler：记录 code、status、path、request_id。
- `RequestValidationError` handler：记录 validation 摘要，不记录敏感原文。
- 通用 `Exception` handler：记录 `exc_info`，客户端返回统一 500 错误结构，不暴露栈信息。

---

## 8. 脱敏与截断

日志写入前统一执行脱敏。默认敏感字段名大小写不敏感，包含：

- `password`
- `token`
- `access_token`
- `refresh_token`
- `authorization`
- `api_key`
- `secret`
- `jwt`
- `captcha`
- `credential`
- `cookie`
- `set-cookie`

脱敏规则：

- 字典按 key 判断，敏感值替换为 `"[REDACTED]"`。
- list 递归处理。
- query 参数递归处理。
- headers 默认只保留安全摘要，Authorization、Cookie、Set-Cookie 不记录原值。
- 字符串超过 `LOG_BODY_MAX_CHARS` 时截断并附带 `truncated=true` 与原始长度。
- Base64、大文本、OCR 原文、LLM prompt/response 等内容除字段名脱敏外，还受长度上限保护。

脱敏必须发生在 JSON Formatter 或写日志前的统一工具函数中，避免业务模块重复实现。

---

## 9. Request ID 与 Celery 贯穿

使用 `contextvars` 保存当前 `request_id`。

API 入站流程：

1. 从 `X-Request-ID` 读取请求 ID。
2. 如果不存在，生成 UUID。
3. 写入 context。
4. 输出所有 API 日志时自动带上。
5. 响应头返回 `X-Request-ID`。

Celery 入队流程：

1. `enqueue_task(...)` 从 context 读取当前 `request_id`。
2. 将 `request_id` 写入 Celery headers。
3. 保留调用方显式传入 headers 的能力；如果调用方已经显式传入 `request_id`，以调用方 headers 中的值为准，否则使用 context 中的当前 `request_id`。

Celery 执行流程：

1. Worker 从 task request headers 读取 `request_id`。
2. 写入 context。
3. 任务执行期间日志自动带上 `request_id` 和 `task_id`。
4. 任务结束后清理 context，避免线程复用串号。

Beat 默认没有 HTTP `request_id`，但日志应带 `process_type=beat` 和调度相关字段。

---

## 10. 关键日志补点

首轮补点按边界优先，避免无意义噪声。

### 10.1 API 边界

HTTP 中间件覆盖全部请求/响应。异常 handler 覆盖业务错误、校验错误和未捕获异常。

### 10.2 Celery 边界

记录任务：

- 入队成功与失败。
- 开始执行。
- 成功完成。
- 失败异常。
- 跳过。
- 重试。

关键字段包括 `task_id`、`task_name`、`queue`、`request_id`、耗时、错误类型。

### 10.3 外部依赖

覆盖：

- LLM HTTP 调用。
- Redis/Celery broker 连接与入队失败。
- 数据库启动建表。
- LangGraph checkpoint 初始化与关闭。
- OCR/翻译外部工具调用。

日志记录耗时、目标摘要、状态、错误类型，不记录密钥或完整文件内容。

### 10.4 核心长流程

覆盖：

- Agent run。
- OCR 初始化扫描。
- 文档翻译 pipeline。
- Celery Beat 调度同步与 reconcile。

关键字段包括 `run_id`、`task_id`、文件数量、任务数量、耗时、失败原因。

---

## 11. 文件滚动与保留

文件 handler 使用 `TimedRotatingFileHandler`：

```python
TimedRotatingFileHandler(
    filename=...,
    when="midnight",
    backupCount=settings.log_retention_days,
    encoding="utf-8",
)
```

日志文件：

- `backend/logs/api.log`
- `backend/logs/worker.log`
- `backend/logs/beat.log`

保留规则：

- 默认保留 7 天。
- 旧日志由 handler 自动删除。
- 日志目录不存在时自动创建。
- `backend/logs/` 不纳入 git。

---

## 12. 测试计划

### 12.1 单元测试

- JSON Formatter 输出基础字段。
- `extra` 字段可合并到 JSON。
- 异常日志包含异常类型和栈摘要。
- 中文内容可正确输出。
- 不可 JSON 序列化对象会转为字符串摘要。
- 脱敏函数处理嵌套 dict/list、query、headers。
- 敏感字段大小写不敏感。
- 长文本截断并记录原始长度。

### 12.2 API 中间件测试

- 请求 body 被记录后业务仍可正常读取。
- 响应 body 被记录后客户端仍收到正确响应。
- 响应头包含 `X-Request-ID`。
- 请求/响应日志包含脱敏后的 body。
- 文件上传或二进制响应只记录摘要。
- 流式响应不被完整消费。
- 未捕获异常记录 `http.error`，客户端不暴露栈。

### 12.3 滚动配置测试

- 不同 `process_type` 选择正确文件名。
- handler 类型为 `TimedRotatingFileHandler`。
- `backupCount` 等于 `LOG_RETENTION_DAYS`。
- 重复初始化不会重复添加 handler。

### 12.4 Celery 贯穿测试

- `enqueue_task(...)` 注入 `request_id` header。
- Worker 任务侧可从 headers 恢复 context。
- 任务日志包含 `request_id` 与 `task_id`。
- 任务结束后 context 被清理。

### 12.5 回归测试

- 现有 LLM、Agent、Translate 相关测试保持通过。
- API 请求/响应行为不因日志中间件改变。
- Celery 现有 Windows 兼容逻辑不被破坏。

---

## 13. 实施顺序

1. 新增日志配置、JSON Formatter、脱敏与 context 工具。
2. 新增 Settings 与 `.env.example`、`.env.dev` 同步。
3. 在 API 与 Celery 入口初始化日志。
4. 新增 API 请求/响应日志中间件。
5. 扩展异常 handler 日志。
6. 为 `enqueue_task(...)` 与 Celery 任务执行补充 `request_id` 贯穿。
7. 按边界为 Agent、OCR、翻译、调度、外部依赖补关键日志。
8. 增加测试。
9. 更新相关文档中的实现对照。

---

## 14. 风险与约束

- 记录 API 报文会增加日志体积，必须依赖 `LOG_BODY_MAX_CHARS`、文件滚动和脱敏策略控制风险。
- 读取请求/响应 body 容易影响 ASGI 流，必须用测试覆盖业务仍可正常读取和返回。
- 流式响应、SSE、文件下载不能为了日志完整性而消费完整响应。
- Celery 线程池或子进程复用时必须清理 context，避免 request_id 串号。
- JSON Formatter 不能因为单条日志中存在不可序列化对象而导致业务日志写入失败。
- 敏感字段规则无法识别所有业务语义，后续新增高风险字段时需要扩展脱敏列表。

---

## 15. 验收标准

- API、Worker、Beat 均输出 JSON 行日志到 stdout。
- API、Worker、Beat 分别写入 `backend/logs/api.log`、`worker.log`、`beat.log`。
- 日志文件按天滚动，默认保留 7 天。
- API 请求与响应报文被记录，敏感字段脱敏，长 body 截断。
- 每个 API 响应带 `X-Request-ID`，同一请求链路日志可通过 `request_id` 检索。
- API 触发的 Celery 任务日志带同一个 `request_id`。
- 未捕获异常写入结构化错误日志，客户端不暴露栈。
- 关键长流程和外部依赖具备可排查的开始、完成、失败日志。
- 新增测试覆盖 Formatter、脱敏、中间件、滚动配置和 Celery request_id 贯穿。

---

## 16. 实现对照（以代码为准，2026-05-23）

| Spec 条目 | 当前代码位置 | 备注 |
| --- | --- | --- |
| JSON 日志 formatter | `backend/app/core/logging_json.py` | 每行一条 JSON，合并 context 与 `extra`，并保护基础字段不被覆盖。 |
| 脱敏与截断 | `backend/app/core/logging_redaction.py` | 敏感字段递归脱敏，长文本截断，tuple 形态保留。 |
| 日志 context | `backend/app/core/logging_context.py` | `request_id` / `task_id` / `process_type` 的 contextvars 管理。 |
| 日志初始化与滚动文件 | `backend/app/core/logging_config.py` | stdout + `TimedRotatingFileHandler`，按进程文件。 |
| 日志 Settings 与 env | `backend/app/config.py`、`backend/.env.example`、`backend/.env.dev` | 7 项日志配置已同步。 |
| API 请求/响应报文日志 | `backend/app/core/logging_middleware.py` | 记录 `http.request`（method、path、query、request_body）；`http.response` 仅 status/duration，**不记录响应 body**；返回 `X-Request-ID`；流式响应不再缓冲 body。 |
| FastAPI 接入 | `backend/app/main.py`、`backend/app/errors.py` | 初始化日志、中间件、异常日志与 500 兜底。 |
| Celery request_id 贯穿 | `backend/app/celery_app.py` | 入队 headers 注入，任务 prerun/postrun 恢复/清理 context。 |
| 关键边界日志 | DB bootstrap、LangGraph checkpoint、Agent run、OCR scan、Translate pipeline、Beat scheduler | 记录开始、结束、失败摘要。 |
| 测试 | `backend/tests/test_logging_*.py`、`backend/tests/test_api_logging_integration.py`、`backend/tests/test_celery_request_logging_context.py` | 45 项 pytest 通过。 |
