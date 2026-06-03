# Backend 日志规范（Minerva）

面向 **backend 业务与基础设施开发者** 的统一日志约定。基础设施细节见 spec；本文是可执行的日常规范。

**权威设计文档：** [`docs/superpowers/specs/2026-06-03-unified-log-tool-design.md`](superpowers/specs/2026-06-03-unified-log-tool-design.md)

**前置能力（2026-05-23 日志框架）：** `configure_logging`、上下文 `ContextVar`、`PatternLogFormatter`、HTTP 中间件、脱敏与滚动文件 — 见 [`docs/superpowers/specs/2026-05-23-backend-logging-framework-design.md`](superpowers/specs/2026-05-23-backend-logging-framework-design.md)（业务 API 以本文与 2026-06-03 spec 为准）。

---

## 1. 业务代码怎么打日志

### 1.1 获取 logger

```python
from app.core.log import get_logger

log = get_logger(__name__)
```

- **必须**使用 `get_logger`，**禁止**在业务模块使用 `logging.getLogger(__name__)` 或 Celery `get_task_logger`。
- 模块内统一变量名 **`log`**（不用 `logger` / `_LOGGER`）。
- 仅 `app/core/logging_config.py` 等配置模块可直接使用 stdlib `logging.getLogger` 管理 root / 第三方 logger 级别。

### 1.2 级别与方法

| 方法 | 级别 | 说明 |
|------|------|------|
| `log.debug(...)` | DEBUG | 诊断信息 |
| `log.info(...)` | INFO | 正常流程 |
| `log.warn(...)` | WARNING | **推荐**（log4j 风格别名） |
| `log.warning(...)` | WARNING | 与 `warn` 等价，新代码优先 `warn` |
| `log.error(...)` | ERROR | 错误 |
| `log.exception(...)` | ERROR | 默认 `exc_info=True` |
| `log.critical(...)` | CRITICAL | 严重故障 |

### 1.3 消息与占位符

使用 **SLF4J / log4j 风格 `{}`**，不用 `%s` 或 f-string 拼日志正文：

```python
# 推荐
log.info("validate token: {}", token)
log.warn("retry exhausted attempts={}", attempts, event="llm.retry")

# 避免
log.info("validate token: %s", token)
log.info(f"validate token: {token}")
```

- 占位符个数必须与参数个数一致；不匹配时框架会打内部 WARNING 并保留原 template。
- 字面量花括号用 `{{` / `}}` 转义。

### 1.4 结构化字段

**优先**用关键字参数写入 trailing `key=value`（由 `PatternLogFormatter` 输出）：

```python
log.info("database bootstrap started", event="db.bootstrap.started")
log.error("bootstrap failed", exc_info=True, event="db.bootstrap.failed")
```

仍支持显式 `extra={...}`（与 kwargs 合并时 **kwargs 覆盖同名 key**）。新代码优先 kwargs，避免混用两种风格。

### 1.5 保留参数（stdlib 透传）

以下关键字按 stdlib 语义处理，**不**进入结构化 `extra`：

- `exc_info`
- `stack_info`
- `stacklevel`
- `extra`

示例：`log.error("failed", exc_info=True)` ✅

### 1.6 级别判断

需要避免昂贵计算时，先判断级别：

```python
import logging

if log.is_enabled_for(logging.DEBUG):
    log.debug("payload {}", expensive_preview())
```

---

## 2. 输出格式

单行文本（log4j 模式），由 `PatternLogFormatter` 生成：

```text
2026-06-03 14:30:01.042 [MainThread] [chat-abc] trace-uuid INFO  app.module.name:88 - message event=foo key=value
```

| 片段 | 来源 |
|------|------|
| 时间戳 | 记录创建时间（毫秒） |
| `[thread]` | `record.threadName` |
| `[x-chat-id]` | `logging_context` → `X-Chat-Id` |
| traceId | `trace_id`，否则 `request_id` |
| level | 左对齐 5 字符 |
| logger:line | logger 名（截断 50）+ 业务调用行号（`stacklevel` 校正） |
| message + fields | 正文 + kwargs/extra 字段 |

异常会追加 traceback。

---

## 3. 进程配置与环境变量

由 `configure_logging(process_type=...)` 在 API / worker / beat 启动时初始化。常用环境变量（见 `backend/.env.example`）：

| 变量 | 含义 |
|------|------|
| `LOG_LEVEL` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `LOG_DIR` | 日志目录（相对 `backend/`） |
| `LOG_RETENTION_DAYS` | 滚动保留天数 |
| `LOG_FILE_ENABLED` / `LOG_STDOUT_ENABLED` | 文件 / 控制台开关 |
| `LOG_BODY_ENABLED` / `LOG_BODY_MAX_CHARS` | HTTP  body 日志 |

**新增或变更 Settings 时**须同步 `backend/.env.example` 与 `backend/.env.dev`（见 minerva-conventions）。

---

## 4. HTTP 与 Celery 上下文

- HTTP：`HttpLoggingMiddleware` 注入 `request_id`、`trace_id`、`x_chat_id`。
- Celery：`celery_app` 通过 task headers 恢复上下文；任务入口使用 `get_logger(__name__)`。

跨进程排查时优先用日志行中的 **traceId / request_id** 关联 API 与 worker。

---

## 5. 敏感信息与脱敏

- 禁止记录：`api_key`、token、密码、完整 Authorization、大块 Base64、未截断文件内容。
- HTTP body 经 `logging_redaction` 脱敏；业务侧调用 LLM/OCR 等继续使用 `text_for_log` / `json_for_log` 等现有 helper。
- `MinervaLogger` **不**自动脱敏 kwargs，避免隐式性能与语义开销。

---

## 6. 测试

- 占位符 / wrapper：`backend/tests/test_log_placeholders.py`、`test_log_wrapper.py`
- 格式 / 中间件 / 配置：`backend/tests/test_logging_*.py`

新增日志行为时优先扩展上述测试。

---

## 7. 实现位置速查

| 组件 | 路径 |
|------|------|
| 业务 API | `backend/app/core/log.py` |
| `{}` 占位符 | `backend/app/core/log_placeholders.py` |
| 进程配置 | `backend/app/core/logging_config.py` |
| 文本格式 | `backend/app/core/logging_text.py` |
| 上下文 | `backend/app/core/logging_context.py` |
| HTTP 日志 | `backend/app/core/logging_middleware.py` |
| 脱敏 | `backend/app/core/logging_redaction.py` |

---

## 8. 历史文档说明

2026-05-23 日志框架 spec 曾约定「保留 `logging.getLogger` + JSON 格式」。当前实现为 **PatternLogFormatter 文本格式 + `get_logger` 封装**（2026-06-03）。阅读旧 plan / 历史 PR 时以 **本文 + 2026-06-03 spec** 为准。
