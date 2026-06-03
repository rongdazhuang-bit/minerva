# Backend 统一日志工具（log4j 风格）设计

**日期**：2026-06-03  
**状态**：已定稿（brainstorming 确认）  
**范围**：在现有 `app/core/logging_*` 基础设施之上，新增 `get_logger` 工厂与 `MinervaLogger` 封装；统一 `{}` 占位符传参与结构化字段写法；对齐 log4j 文本格式；**本期全量迁移** `backend/app/` 下所有 `logging.getLogger` 调用。仅 Backend（Python），不含 Frontend。

**关联文档**：

- `backend/app/core/logging_config.py`（进程级配置，不变更职责）
- `backend/app/core/logging_context.py`（MDC 等价物：request_id / trace_id / x_chat_id 等）
- `backend/app/core/logging_text.py`（PatternLogFormatter）
- `.cursor/skills/minerva-conventions/SKILL.md`（环境变量变更须同步 `.env.example` / `.env.dev`；本期无新增环境变量）

---

## 1. 目标与成功标准

### 1.1 目标

1. 提供 **log4j / SLF4J 风格** 的业务侧日志 API：`get_logger(__name__)` + `log.info` / `log.warn` / `log.error` / `log.debug` 等级别方法。
2. 支持 **`{}` 占位符** 传参：`log.info("validate token: {}", token)`，替代 `%s` 与 f-string 混用。
3. 支持 **结构化字段** 两种写法并存：关键字参数 `event="auth.validate"` 与显式 `extra={...}`。
4. 日志行格式统一为 log4j 模式（见 §4），在现有 `PatternLogFormatter` 上校验/微调。
5. **全量迁移** 业务代码：统一 import 与调用风格，消除 `log` / `logger` / `_LOGGER` 命名不一致。

### 1.2 成功标准

- 新增 `app/core/log.py`（及占位符辅助模块），单元测试覆盖占位符、kwargs 合并、行号、格式。
- `backend/app/` 内无直接 `logging.getLogger(__name__)` 业务用法（`logging_config` 等基础设施模块除外）。
- 现有 logging 集成测试（config / middleware / context / formatter）全部通过；新增 wrapper 测试通过。
- 日志输出仍经 `configure_logging` 配置的 QueueHandler + 文件/stdout，上下文变量（`x_chat_id`、`trace_id`）自动注入格式行。
- 无新增环境变量；`configure_logging` 对外接口不变。

### 1.3 需求决策摘要（brainstorming 定稿）

| 项 | 决策 |
|----|------|
| 范围 | 仅 Backend（Python） |
| Logger 获取 | **方案 A**：`get_logger(__name__)` 工厂 |
| 结构化字段 | **方案 C**：kwargs + `extra=` 兼容 |
| 占位符 | `{}` 顺序替换，支持 `{{` / `}}` 转义 |
| 输出格式 | log4j 模式（§4） |
| 实现策略 | **方案 1**：Wrapper 封装 stdlib Logger（非继承、非全局 setLoggerClass） |
| 迁移 | **全量替换** 业务模块 + 相关测试 |
| `warn` | 作为 `warning` 别名 |

---

## 2. 总体架构

```
业务模块
  log = get_logger(__name__)
  log.info("validate token: {}", token, event="auth.validate")
        │
        ▼
  MinervaLogger（app/core/log.py）
    ├─ format_placeholders(message, *args)   ← app/core/log_placeholders.py
    ├─ merge extras: extra= ∪ kwargs
    └─ delegate → stdlib logging.Logger
              │  stacklevel 校正 → 行号指向业务代码
              ▼
  现有链路（不变）
    QueueHandler → PatternLogFormatter → stdout / 滚动文件
    logging_context（ContextVar）→ 格式行中的 x_chat_id / traceId
```

### 2.1 不在本期范围

- Frontend 日志工具
- 启用 `JsonLogFormatter` 或新增 `LOG_FORMAT=json` 配置
- 日志采集/告警平台对接
- 修改 `logging_redaction` 规则（HTTP 中间件等继续沿用）

---

## 3. API 设计

### 3.1 模块入口

```python
from app.core.log import get_logger

log = get_logger(__name__)
```

- `get_logger(name: str) -> MinervaLogger`：内部 `logging.getLogger(name)` 并包装为单例缓存（同一 `name` 返回同一 wrapper 实例，避免重复包装开销）。

### 3.2 MinervaLogger 方法

| 方法 | 说明 |
|------|------|
| `debug(msg, *args, **kwargs)` | DEBUG |
| `info(msg, *args, **kwargs)` | INFO |
| `warn(msg, *args, **kwargs)` | WARNING 别名 |
| `warning(msg, *args, **kwargs)` | WARNING |
| `error(msg, *args, **kwargs)` | ERROR |
| `critical(msg, *args, **kwargs)` | CRITICAL |
| `exception(msg, *args, **kwargs)` | ERROR + 默认 `exc_info=True` |
| `is_enabled_for(level)` | 透传底层 Logger |
| `name` 属性 | 透传底层 logger 名 |

### 3.3 参数语义

**位置参数 `*args`**：仅用于替换 `msg` 中的 `{}` 占位符（SLF4J 风格）。

**保留关键字**（透传 stdlib，不进入 `extra`）：

- `exc_info`
- `stack_info`
- `stacklevel`（wrapper 会在用户未指定时默认叠加偏移，见 §3.5）
- `extra`

**其余 `**kwargs`**：合并进 `extra` 字典，供 `PatternLogFormatter._extra_fields` 输出为 trailing `key=value`。

**`extra` 与 kwargs 合并规则**：

1. 先复制 `extra`（若提供）。
2. kwargs 写入同名 key 时 **覆盖** `extra` 中已有字段。
3. kwargs 中的 key 不得与保留关键字冲突；冲突时 raise `TypeError`（fail fast，便于测试）。

**示例**：

```python
log.info("validate token: {}", token, event="auth.validate")
log.warn("retry", attempts=3, extra={"component": "llm"})
log.error("bootstrap failed", exc_info=True, event="db.bootstrap.failed")
log.debug("skip reason: {}", reason)
```

### 3.4 `{}` 占位符规则（`log_placeholders.py`）

1. 从左到右依次替换每个未转义的 `{}`。
2. `{{` → 字面量 `{`；`}}` → 字面量 `}`。
3. **参数个数必须等于占位符个数**；不匹配时：
   - 记录一条 **WARNING**（使用底层 logger，避免递归）说明 template / 期望 / 实际个数；
   - 消息原样输出（占位符保留），不抛异常到业务层。
4. 不支持 `{name}` 命名占位符（YAGNI）；仅 `{}` 顺序替换。
5. 替换后的值经 `format_log_value`（复用 `logging_text`）或等价逻辑格式化，与现有 trailing extras 风格一致。

### 3.5 行号（`%L` / `record.lineno`）

委托 stdlib 时设置 `stacklevel`：

- wrapper 默认：`stacklevel = (kwargs.get("stacklevel") or 1) + 1`
- 保证 `PatternLogFormatter` 中 `:lineno` 指向 **业务调用行**，而非 `MinervaLogger.info` 内部。

### 3.6 与 stdlib 的边界

- 基础设施模块（`logging_config.py`、`logging_middleware.py` 内部专用 logger 名如 `app.http`）迁移为 `get_logger("app.http")`，仍走同一 wrapper。
- `configure_logging` 内部继续使用 `logging.getLogger` 配置 root 与第三方 logger 级别，**不**包装。

---

## 4. 日志格式

目标 log4j 模式：

```
%d{yyyy-MM-dd HH:mm:ss.SSS} [%thread] [%X{x-chat-id}] %X{traceId} %-5level %logger{50}:%L - %msg%n
```

与现有 `PatternLogFormatter` 对齐关系：

| log4j 片段 | 现有实现 | 本期动作 |
|------------|----------|----------|
| `%d{yyyy-MM-dd HH:mm:ss.SSS}` | `%Y-%m-%d %H:%M:%S` + `.mmm` | 保持 |
| `[%thread]` | `[{record.threadName}]` | 保持 |
| `[%X{x-chat-id}]` | `[{x_chat_id}]`（空则 `[]`） | 保持 |
| `%X{traceId}` | `trace_id`，fallback `request_id` | 保持；与 context 一致 |
| `%-5level` | `levelname` 左对齐 5 字符 | 保持 |
| `%logger{50}:%L` | logger 名截断 50 + `:{lineno}` | 保持 |
| `%msg` + extras | message + trailing `key=value` | 保持 |
| `%n` + exception | 换行 + traceback | 保持 |

若集成测试发现与上述模式字面差异，仅在 `PatternLogFormatter` 做最小修正。

**示例行**：

```
2026-06-03 14:30:01.042 [MainThread] [chat-abc] req-uuid-123 INFO  app.agent.service.agent_graph_run_service:88 - run started event=agent.run.started session_id=...
```

---

## 5. 迁移计划

### 5.1 新增文件

| 文件 | 职责 |
|------|------|
| `backend/app/core/log.py` | `get_logger`、`MinervaLogger` |
| `backend/app/core/log_placeholders.py` | `{}` 解析与替换 |
| `backend/tests/test_log_wrapper.py` | wrapper 行为测试 |
| `backend/tests/test_log_placeholders.py` | 占位符边界测试 |

### 5.2 修改文件（全量）

替换 `backend/app/` 下所有业务 `logging.getLogger`（约 40+ 处，以 grep 为准），包括但不限于：

- `app/agent/**`
- `app/llm/**`
- `app/file_ocr/**`
- `app/translate/**`
- `app/ocr/**`
- `app/sys/celery/**`
- `app/core/infrastructure/**`
- `app/core/logging_middleware.py`
- `app/celery_app.py`
- `app/errors.py`

**迁移步骤（每个文件）**：

1. `import logging` → `from app.core.log import get_logger`（若仍需 `logging` 常量如 `logging.INFO` 则保留 import）。
2. `log = logging.getLogger(__name__)` → `log = get_logger(__name__)`。
3. 统一变量名为 **`log`**（废弃 `logger`、`_LOGGER`）。
4. 将 `%s` / f-string 消息改为 `{}` 占位符（同一文件内一并整理）。
5. 将 `extra={"event": ...}` 可简化为 kwargs `event=...`（可选优化，不强制删 extra）。

**不迁移**：`logging_config.py` 内对 root/uvicorn/celery/sqlalchemy 的配置性 `getLogger` 调用。

### 5.3 测试更新

- 现有 `test_logging_*.py` 保持通过；若 mock `logging.getLogger`，改为 mock `get_logger` 或 patch 底层 logger。
- 新增 wrapper / placeholder 单测（§7）。

---

## 6. 错误处理与可观测性

| 场景 | 行为 |
|------|------|
| 占位符个数 ≠ args 个数 | WARNING 内部日志 + 原 template 输出 |
| kwargs 使用保留关键字名 | `TypeError` |
| `exc_info=True` / `log.exception` | 与 stdlib 一致，formatter 追加 traceback |
| 敏感字段 | 业务侧继续用 `logging_redaction`；wrapper 不自动脱敏（避免隐式性能开销） |
| DEBUG 关闭 | stdlib level 判断不变；不引入 lazy lambda API（YAGNI） |

---

## 7. 测试设计

### 7.1 单元测试 — `log_placeholders`

- 0 / 1 / N 个 `{}` 替换
- `{{` / `}}` 转义
- args 过多 / 过少
- 含空格、`=`` 的字符串值格式化

### 7.2 单元测试 — `MinervaLogger`

- kwargs 进入 formatted trailing fields
- `extra` 与 kwargs 合并及覆盖优先级
- `warn` 与 `warning` 等价
- `stacklevel` 行号指向调用方（caplog + 检查 record.lineno）
- `exception` 默认带 exc_info

### 7.3 集成测试

- `configure_logging` + `get_logger` 输出一行符合 §4 模式（可复用/扩展现有 `test_logging_pattern_formatter.py`）
- HTTP middleware 使用 `get_logger("app.http")` 后行为不变

---

## 8. 规格自检（2026-06-03）

| 项 | 结论 |
|----|------|
| 占位符 / TBD | 无 TBD；占位符不匹配策略已明确（内部 WARNING + 原样输出） |
| 一致性 | Wrapper 委托 stdlib，与现有 Formatter/Handler/Context 架构一致 |
| 范围 | 单特性（统一 Logger API + 全量迁移），适合一份实现计划 |
| 歧义 | kwargs 覆盖 extra 同名 key；不支持命名 `{}`；无 lazy logging |
| 环境变量 | 本期无新增/变更 |

---

## 9. 后续工作入口

用户审阅本 spec 并确认后，使用 **`writing-plans`** 产出分步实现清单（`docs/superpowers/plans/2026-06-03-unified-log-tool.md`）。
