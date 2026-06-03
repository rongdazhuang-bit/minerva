# Backend 统一日志工具（log4j 风格）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 `app/core/logging_*` 基础设施上新增 `get_logger` + `MinervaLogger` 封装，支持 `{}` 占位符与 kwargs/extra 结构化字段，并全量迁移 `backend/app/` 业务模块的 `logging.getLogger` 调用。

**Architecture:** `MinervaLogger` 薄包装 stdlib `logging.Logger`：占位符替换在 `log_placeholders.py`，kwargs 合并进 `extra` 后委托底层 logger，并通过 `stacklevel` 校正行号。现有 `configure_logging`、`PatternLogFormatter`、`logging_context` 不变。

**Tech Stack:** Python 3.11+, stdlib `logging`, pytest, 现有 `PatternLogFormatter` / `format_log_value`。

**Spec:** `docs/superpowers/specs/2026-06-03-unified-log-tool-design.md`  
**Developer guide:** `docs/backend-logging.md`

---

## Scope Check

单计划、可独立验证的分期：

| 阶段 | 交付物 | 可独立验证 |
|------|--------|------------|
| A | `log_placeholders` + 单测 | placeholder 测试全绿 |
| B | `MinervaLogger` + `get_logger` + 单测 | wrapper 测试全绿 |
| C | 格式集成测试（可选微调 formatter） | pattern formatter 测试全绿 |
| D | 全量业务迁移（~40 文件） | grep 无业务 `logging.getLogger` |
| E | 全量 pytest + 文档回填 | 全测试通过 |

---

## File Structure

### 新建

| 路径 | 职责 |
|------|------|
| `backend/app/core/log_placeholders.py` | `{}` 占位符解析、转义、值格式化 |
| `backend/app/core/log.py` | `PlaceholderResult`、`MinervaLogger`、`get_logger` 工厂与缓存 |
| `backend/tests/test_log_placeholders.py` | 占位符单测 |
| `backend/tests/test_log_wrapper.py` | wrapper 行为单测 |

### 修改（基础设施）

| 路径 | 变更 |
|------|------|
| `backend/app/core/logging_middleware.py` | `get_logger("app.http")` |
| `backend/app/core/logging_text.py` | 仅当集成测试发现格式偏差时微调 |
| `backend/tests/test_logging_pattern_formatter.py` | 追加 `get_logger` 集成用例（可选） |

### 修改（业务迁移 — 共 40 文件）

**不修改：** `backend/app/core/logging_config.py`（配置性 `logging.getLogger` 保留）

| 包 | 文件 |
|----|------|
| `app/core` | `infrastructure/db/bootstrap.py`, `logging_middleware.py` |
| `app` | `celery_app.py`, `errors.py` |
| `app/agent` | `service/agent_graph_run_service.py`, `service/memory_compress_service.py`, `service/memory_extract_llm.py`, `service/memory_persist_service.py`, `service/mem0_llm_client.py`, `infrastructure/langgraph_checkpointer.py`, `infrastructure/skill_loader.py`, `task/checkpoint_purge_job.py`, `task/memory_compress_job.py`, `skills/ppt/pptmaker/layout_select.py`, `memory/sql/persist.py`, `memory/mem0/persist.py`, `memory/mem0/retrieve.py`, `memory/mem0/embedder_config.py`, `memory/mem0/profile_runtime.py`, `memory/mem0/spacy_runtime.py`, `memory/mem0/logging_embedder.py`, `memory/mem0/logging_neo4j.py` |
| `app/llm` | `service/llm_service.py`, `strategies/http_common.py`, `strategies/text_chat.py` |
| `app/file_ocr` | `service/scan_init.py`, `service/markdown_pages.py`, `service/layout_pages.py`, `service/paddle_ocr_request.py`, `service/paddle_markdown_images.py`, `service/result_row_cleanup.py`, `service/strategies/mineru.py`, `service/strategies/paddle.py` |
| `app/translate` | `service/run_pipeline.py`, `service/layout_pages.py`, `service/office_convert.py` |
| `app/ocr` | `mineru/client.py`, `paddleocr/client.py` |
| `app/sys/celery` | `beat/minerva_scheduler.py`, `service/scheduled_task_guard.py` |

### Docs

| 路径 | 变更 |
|------|------|
| `docs/superpowers/specs/2026-06-03-unified-log-tool-design.md` | 状态改为「已实现」+ 实现对照（Task 10） |

---

## Task 1: `{}` 占位符模块

**Files:**
- Create: `backend/app/core/log_placeholders.py`
- Create: `backend/tests/test_log_placeholders.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_log_placeholders.py`:

```python
"""Tests for SLF4J-style {} log placeholders."""

from __future__ import annotations

from app.core.log_placeholders import PlaceholderResult, format_placeholders


def test_format_placeholders_zero_args() -> None:
    """Messages without placeholders pass through unchanged."""

    result = format_placeholders("database bootstrap started")

    assert result == PlaceholderResult(
        message="database bootstrap started",
        matched=True,
        expected=0,
        provided=0,
    )


def test_format_placeholders_single_arg() -> None:
    """One {} is replaced with a formatted value."""

    result = format_placeholders("validate token: {}", "abc-123")

    assert result.matched is True
    assert result.message == "validate token: abc-123"


def test_format_placeholders_multiple_args() -> None:
    """Multiple {} placeholders are replaced in order."""

    result = format_placeholders("a {} b {}", 1, 2)

    assert result.matched is True
    assert result.message == "a 1 b 2"


def test_format_placeholders_escapes_braces() -> None:
    """Doubled braces render literal brace characters."""

    result = format_placeholders("{{literal}} and {}", "x")

    assert result.matched is True
    assert result.message == "{literal} and x"


def test_format_placeholders_quotes_strings_with_spaces() -> None:
    """String values with whitespace are repr-quoted like format_log_value."""

    result = format_placeholders("user={}", "hello world")

    assert result.matched is True
    assert result.message == "user='hello world'"


def test_format_placeholders_too_few_args() -> None:
    """Too few args returns the original template and matched=False."""

    result = format_placeholders("a {} b {}", 1)

    assert result.matched is False
    assert result.expected == 2
    assert result.provided == 1
    assert result.message == "a {} b {}"


def test_format_placeholders_too_many_args() -> None:
    """Too many args returns the original template and matched=False."""

    result = format_placeholders("only {}", 1, 2)

    assert result.matched is False
    assert result.expected == 1
    assert result.provided == 2
    assert result.message == "only {}"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_log_placeholders.py -v`

Expected: FAIL — `ModuleNotFoundError: app.core.log_placeholders`

- [ ] **Step 3: 实现占位符模块**

Create `backend/app/core/log_placeholders.py`:

```python
"""SLF4J-style {} placeholder formatting for Minerva log messages."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.logging_text import format_log_value


@dataclass(frozen=True)
class PlaceholderResult:
    """Outcome of formatting one log message template."""

    message: str
    matched: bool
    expected: int
    provided: int


def format_placeholders(template: str, *args: object) -> PlaceholderResult:
    """Replace unescaped `{}` placeholders with formatted argument values."""

    parts: list[str] = []
    arg_index = 0
    placeholder_count = 0
    index = 0
    while index < len(template):
        if template.startswith("{{", index):
            parts.append("{")
            index += 2
            continue
        if template.startswith("}}", index):
            parts.append("}")
            index += 2
            continue
        if template.startswith("{}", index):
            placeholder_count += 1
            if arg_index >= len(args):
                return PlaceholderResult(
                    message=template,
                    matched=False,
                    expected=placeholder_count,
                    provided=len(args),
                )
            parts.append(format_log_value(args[arg_index]))
            arg_index += 1
            index += 2
            continue
        parts.append(template[index])
        index += 1

    if placeholder_count != len(args):
        return PlaceholderResult(
            message=template,
            matched=False,
            expected=placeholder_count,
            provided=len(args),
        )
    return PlaceholderResult(
        message="".join(parts),
        matched=True,
        expected=placeholder_count,
        provided=len(args),
    )
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_log_placeholders.py -v`

Expected: 7 passed

- [ ] **Step 5: Commit**

```powershell
cd d:\ityeahProjects\minerva
git add backend/app/core/log_placeholders.py backend/tests/test_log_placeholders.py
git commit -m "feat(log): add SLF4J-style placeholder formatter"
```

---

## Task 2: MinervaLogger 与 get_logger

**Files:**
- Create: `backend/app/core/log.py`
- Create: `backend/tests/test_log_wrapper.py`

- [ ] **Step 1: 写失败测试**

Create `backend/tests/test_log_wrapper.py`:

```python
"""Tests for MinervaLogger wrapper and get_logger factory."""

from __future__ import annotations

import logging
import sys

import pytest

from app.core.log import MinervaLogger, get_logger


@pytest.fixture(autouse=True)
def _reset_logger_cache() -> None:
    """Ensure each test gets a fresh wrapper cache."""

    import app.core.log as log_module

    log_module._LOGGER_CACHE.clear()
    yield
    log_module._LOGGER_CACHE.clear()


def test_get_logger_returns_cached_wrapper() -> None:
    """Same name returns the same MinervaLogger instance."""

    first = get_logger("app.test.cache")
    second = get_logger("app.test.cache")

    assert first is second
    assert isinstance(first, MinervaLogger)
    assert first.name == "app.test.cache"


def test_info_replaces_placeholders(caplog: pytest.LogCaptureFixture) -> None:
    """info() replaces {} placeholders before delegating to stdlib."""

    caplog.set_level(logging.INFO)
    log = get_logger("app.test.placeholder")

    log.info("validate token: {}", "tok-1", event="auth.validate")

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.message == "validate token: tok-1"
    assert record.event == "auth.validate"
    assert record.levelname == "INFO"


def test_kwargs_override_extra(caplog: pytest.LogCaptureFixture) -> None:
    """Keyword fields override duplicate keys from extra."""

    caplog.set_level(logging.INFO)
    log = get_logger("app.test.merge")

    log.info("retry", extra={"component": "llm", "attempts": 1}, attempts=3)

    record = caplog.records[0]
    assert record.component == "llm"
    assert record.attempts == 3


def test_reserved_kwargs_raise_type_error() -> None:
    """Structured kwargs must not reuse stdlib reserved names."""

    log = get_logger("app.test.reserved")

    with pytest.raises(TypeError, match="exc_info"):
        log.info("bad", exc_info="not-a-flag")


def test_warn_aliases_warning(caplog: pytest.LogCaptureFixture) -> None:
    """warn() emits WARNING level records."""

    caplog.set_level(logging.WARNING)
    log = get_logger("app.test.warn")

    log.warn("slow path")

    assert caplog.records[0].levelname == "WARNING"


def test_exception_sets_exc_info(caplog: pytest.LogCaptureFixture) -> None:
    """exception() defaults exc_info=True."""

    caplog.set_level(logging.ERROR)
    log = get_logger("app.test.exception")

    try:
        raise RuntimeError("boom")
    except RuntimeError:
        log.exception("failed hard")

    record = caplog.records[0]
    assert record.levelname == "ERROR"
    assert record.exc_info is not None
    assert record.exc_info[0] is RuntimeError


def test_mismatch_emits_internal_warning(caplog: pytest.LogCaptureFixture) -> None:
    """Placeholder mismatch keeps the template and logs an internal warning."""

    caplog.set_level(logging.WARNING)
    log = get_logger("app.test.mismatch")

    log.info("a {} b {}", 1)

    assert len(caplog.records) == 2
    assert caplog.records[0].levelname == "WARNING"
    assert "placeholder mismatch" in caplog.records[0].message
    assert caplog.records[1].message == "a {} b {}"


def test_stacklevel_points_to_caller() -> None:
    """Delegated records use the business caller line number."""

    log = get_logger("app.test.stacklevel")
    underlying = log._underlying
    captured: list[logging.LogRecord] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _CaptureHandler()
    underlying.addHandler(handler)
    underlying.setLevel(logging.INFO)
    try:
        def _emit_from_helper() -> None:
            log.info("helper line")

        _emit_from_helper()
    finally:
        underlying.removeHandler(handler)

    assert captured
    assert captured[0].lineno == _emit_from_helper.__code__.co_firstlineno + 1
```

- [ ] **Step 2: 运行测试确认失败**

Run: `cd backend && python -m pytest tests/test_log_wrapper.py -v`

Expected: FAIL — `ModuleNotFoundError: app.core.log`

- [ ] **Step 3: 实现 MinervaLogger**

Create `backend/app/core/log.py`:

```python
"""Log4j-style logger factory and MinervaLogger wrapper."""

from __future__ import annotations

import logging
from typing import Any

from app.core.log_placeholders import format_placeholders

# Stdlib logging kwargs that must not be treated as structured fields.
_RESERVED_KWARGS = frozenset({"exc_info", "stack_info", "stacklevel", "extra"})
# Cached wrappers keyed by logger name.
_LOGGER_CACHE: dict[str, MinervaLogger] = {}


class MinervaLogger:
    """Thin wrapper around stdlib Logger with {} placeholders and kwargs extras."""

    def __init__(self, underlying: logging.Logger) -> None:
        """Bind one stdlib logger instance."""

        self._underlying = underlying

    @property
    def name(self) -> str:
        """Return the wrapped logger name."""

        return self._underlying.name

    def is_enabled_for(self, level: int) -> bool:
        """Return whether the wrapped logger accepts the given level."""

        return self._underlying.isEnabledFor(level)

    def debug(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a DEBUG message."""

        self._emit(logging.DEBUG, msg, *args, **kwargs)

    def info(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log an INFO message."""

        self._emit(logging.INFO, msg, *args, **kwargs)

    def warn(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a WARNING message (log4j-style alias)."""

        self._emit(logging.WARNING, msg, *args, **kwargs)

    def warning(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a WARNING message."""

        self._emit(logging.WARNING, msg, *args, **kwargs)

    def error(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log an ERROR message."""

        self._emit(logging.ERROR, msg, *args, **kwargs)

    def critical(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log a CRITICAL message."""

        self._emit(logging.CRITICAL, msg, *args, **kwargs)

    def exception(self, msg: str, *args: object, **kwargs: Any) -> None:
        """Log an ERROR message with exception info."""

        if "exc_info" not in kwargs:
            kwargs["exc_info"] = True
        self._emit(logging.ERROR, msg, *args, **kwargs)

    def _emit(self, level: int, msg: str, *args: object, **kwargs: Any) -> None:
        """Format placeholders, merge extras, and delegate to stdlib."""

        reserved = {key: kwargs.pop(key) for key in list(kwargs) if key in _RESERVED_KWARGS}
        for key in kwargs:
            if key in _RESERVED_KWARGS:
                raise TypeError(f"structured log field {key!r} conflicts with logging reserved keyword")

        result = format_placeholders(msg, *args)
        if not result.matched:
            self._underlying.warning(
                "log placeholder mismatch template=%r expected=%s provided=%s",
                msg,
                result.expected,
                result.provided,
                stacklevel=(reserved.get("stacklevel") or 1) + 2,
            )
            message = result.message
        else:
            message = result.message

        merged_extra: dict[str, Any] = dict(reserved.get("extra") or {})
        merged_extra.update(kwargs)

        log_kwargs: dict[str, Any] = {
            "stacklevel": (reserved.get("stacklevel") or 1) + 1,
        }
        if "exc_info" in reserved:
            log_kwargs["exc_info"] = reserved["exc_info"]
        if "stack_info" in reserved:
            log_kwargs["stack_info"] = reserved["stack_info"]
        if merged_extra:
            log_kwargs["extra"] = merged_extra

        self._underlying.log(level, message, **log_kwargs)


def get_logger(name: str) -> MinervaLogger:
    """Return a cached MinervaLogger for the given stdlib logger name."""

    cached = _LOGGER_CACHE.get(name)
    if cached is None:
        cached = MinervaLogger(logging.getLogger(name))
        _LOGGER_CACHE[name] = cached
    return cached
```

- [ ] **Step 4: 运行测试确认通过**

Run: `cd backend && python -m pytest tests/test_log_wrapper.py -v`

Expected: 8 passed

- [ ] **Step 5: Commit**

```powershell
git add backend/app/core/log.py backend/tests/test_log_wrapper.py
git commit -m "feat(log): add MinervaLogger wrapper and get_logger factory"
```

---

## Task 3: 格式集成验证

**Files:**
- Modify: `backend/tests/test_logging_pattern_formatter.py`
- Modify: `backend/app/core/logging_text.py`（仅测试失败时）

- [ ] **Step 1: 追加集成测试**

Append to `backend/tests/test_logging_pattern_formatter.py`:

Add at module top if missing: `import pytest`.

Append:

```python
def test_get_logger_output_matches_pattern_layout(caplog: pytest.LogCaptureFixture) -> None:
    """MinervaLogger records format to the log4j-style pattern layout."""

    from app.core.log import get_logger
    from app.core.logging_context import use_logging_context

    caplog.set_level(logging.INFO)
    log = get_logger("app.test.pattern")

    with use_logging_context(x_chat_id="chat-9", trace_id="trace-9"):
        log.info("run started", event="agent.run.started")

    assert len(caplog.records) == 1
    line = PatternLogFormatter().format(caplog.records[0])

    assert "[chat-9]" in line
    assert "trace-9" in line
    assert "INFO" in line
    assert "app.test.pattern:" in line
    assert "run started event=agent.run.started" in line
```

- [ ] **Step 2: 运行测试**

Run: `cd backend && python -m pytest tests/test_logging_pattern_formatter.py tests/test_log_wrapper.py -v`

Expected: all passed. If layout assertion fails, adjust `PatternLogFormatter.format` minimally in `logging_text.py` to match spec §4 (timestamp/thread/x_chat_id/traceId/level/logger:line - message).

- [ ] **Step 3: Commit（若有改动）**

```powershell
git add backend/tests/test_logging_pattern_formatter.py backend/app/core/logging_text.py
git commit -m "test(log): verify get_logger output matches pattern formatter"
```

---

## Task 4: 迁移 core / celery / errors

**Files:**
- Modify: `backend/app/core/logging_middleware.py`
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`
- Modify: `backend/app/celery_app.py`
- Modify: `backend/app/errors.py`

- [ ] **Step 1: 迁移 logging_middleware.py**

Replace:

```python
import logging
...
_HTTP_LOGGER = logging.getLogger("app.http")
```

With:

```python
from app.core.log import get_logger
...
log = get_logger("app.http")
```

Rename `_emit_http_log` body to use `log.info(message, **fields)` instead of `_HTTP_LOGGER.info(message, extra=fields)`.

- [ ] **Step 2: 迁移 bootstrap.py**

Replace:

```python
import logging
logger = logging.getLogger(__name__)
```

With:

```python
from app.core.log import get_logger
log = get_logger(__name__)
```

Rename all `logger.` → `log.` and convert calls like:

```python
logger.info("database bootstrap skipped", extra={"event": "db.bootstrap.skipped"})
```

To:

```python
log.info("database bootstrap skipped", event="db.bootstrap.skipped")
```

Convert `%s` messages to `{}` in the same file.

- [ ] **Step 3: 迁移 celery_app.py**

Replace `logger = logging.getLogger(__name__)` with `log = get_logger(__name__)`. Keep comment mentioning stdlib if needed; rename `logger.` → `log.`.

- [ ] **Step 4: 迁移 errors.py**

Replace `logger = logging.getLogger(__name__)` with `log = get_logger(__name__)`; update call sites to `{}` placeholders where applicable.

- [ ] **Step 5: 运行相关测试**

Run: `cd backend && python -m pytest tests/test_logging_middleware.py tests/test_logging_config.py tests/test_celery_request_logging_context.py -v`

Expected: all passed

- [ ] **Step 6: Commit**

```powershell
git add backend/app/core/logging_middleware.py backend/app/core/infrastructure/db/bootstrap.py backend/app/celery_app.py backend/app/errors.py
git commit -m "refactor(log): migrate core modules to get_logger"
```

---

## Task 5: 迁移 app/agent 模块

**Files:**（19 个，见 File Structure 表）

- [ ] **Step 1: 批量替换 import 与 logger 变量**

对每个文件执行：

1. 删除 `import logging`（若文件不再直接使用 `logging` 常量）。
2. 添加 `from app.core.log import get_logger`。
3. `log = logging.getLogger(__name__)` → `log = get_logger(__name__)`；`_LOGGER`/`logger` 统一为 `log`。
4. 将所有 `log.info("... %s ...", x)` / f-string 改为 `log.info("... {} ...", x)`。
5. 将 `extra={"event": "..."}` 简化为 kwargs `event="..."`（同文件内一并整理）。

**示例 — `backend/app/agent/infrastructure/langgraph_checkpointer.py`：**

Before:

```python
import logging
log = logging.getLogger(__name__)
...
log.info(
    "langgraph checkpointer ready",
    extra={"event": "agent.checkpointer.ready"},
)
```

After:

```python
from app.core.log import get_logger

log = get_logger(__name__)
...
log.info("langgraph checkpointer ready", event="agent.checkpointer.ready")
```

**示例 — `backend/app/llm/strategies/text_chat.py`：**

Before:

```python
log.info("ai chat.completions request method=stream url=%s body=%s", url, json_for_log(body))
```

After:

```python
log.info("ai chat.completions request method=stream url={} body={}", url, json_for_log(body))
```

- [ ] **Step 2: 运行 agent 相关测试**

Run: `cd backend && python -m pytest tests/test_agent_memory_factory.py tests/test_mem0_logging_embedder.py tests/test_mem0_logging_neo4j.py -v`

Expected: all passed

- [ ] **Step 3: Commit**

```powershell
git add backend/app/agent
git commit -m "refactor(log): migrate agent modules to get_logger"
```

---

## Task 6: 迁移 app/llm、file_ocr、translate、ocr、sys/celery

**Files:**（21 个，见 File Structure 表）

- [ ] **Step 1: 按 Task 5 相同规则迁移剩余包**

重点文件与典型改动：

| 文件 | 改动要点 |
|------|----------|
| `llm/strategies/http_common.py` | `%s` → `{}`；保留 `json_for_log` 调用 |
| `llm/service/llm_service.py` | `logger` → `log` |
| `file_ocr/service/*` | `_LOGGER` → `log` |
| `translate/service/run_pipeline.py` | 长流程 `%s` 全改 `{}` |
| `ocr/mineru/client.py`, `ocr/paddleocr/client.py` | `_LOGGER` → `log` |
| `sys/celery/beat/minerva_scheduler.py` | `_LOGGER` → `log` |

- [ ] **Step 2: 运行广域测试**

Run: `cd backend && python -m pytest tests/test_logging_middleware.py tests/test_logging_config.py tests/test_log_wrapper.py tests/test_log_placeholders.py -v`

Expected: all passed

- [ ] **Step 3: Commit**

```powershell
git add backend/app/llm backend/app/file_ocr backend/app/translate backend/app/ocr backend/app/sys
git commit -m "refactor(log): migrate llm/file_ocr/translate/ocr/sys modules to get_logger"
```

---

## Task 7: 全量验证与 grep 门禁

**Files:** 无新增

- [ ] **Step 1: grep 确认无业务侧 stdlib getLogger**

Run:

```powershell
cd d:\ityeahProjects\minerva\backend
rg "logging\.getLogger" app --glob "*.py"
```

Expected: 仅 `app/core/logging_config.py`（及注释中的提及）命中；**无**业务模块 `logging.getLogger(__name__)`。

- [ ] **Step 2: 全量 pytest**

Run: `cd backend && python -m pytest -q`

Expected: all passed

- [ ] **Step 3: Commit（若有遗漏修复）**

```powershell
git add -A backend/app
git commit -m "refactor(log): complete get_logger migration cleanup"
```

---

## Task 8: 文档回填

**Files:**
- Modify: `docs/superpowers/specs/2026-06-03-unified-log-tool-design.md`

- [ ] **Step 1: 更新 spec 状态与实现对照**

在 spec 文首更新：

```markdown
**状态**：已实现（2026-06-03）
**计划**：`docs/superpowers/plans/2026-06-03-unified-log-tool.md`
```

追加 §10 实现对照：

| 项 | 代码位置 |
|----|----------|
| get_logger / MinervaLogger | `backend/app/core/log.py` |
| {} 占位符 | `backend/app/core/log_placeholders.py` |
| 格式 | `backend/app/core/logging_text.py` — `PatternLogFormatter` |
| HTTP 日志 | `backend/app/core/logging_middleware.py` — `get_logger("app.http")` |

- [ ] **Step 2: Commit**

```powershell
git add docs/superpowers/specs/2026-06-03-unified-log-tool-design.md
git commit -m "docs: mark unified log tool spec as implemented"
```

---

## Spec Self-Review（计划自检）

| Spec 要求 | 对应 Task |
|-----------|-----------|
| get_logger(__name__) 工厂 | Task 2 |
| log.info/warn/error/debug/exception | Task 2 |
| `{}` 占位符 + 转义 | Task 1 |
| kwargs + extra 合并，kwargs 覆盖 | Task 2 测试 |
| 占位符不匹配 → 内部 WARNING | Task 2 测试 |
| stacklevel 行号校正 | Task 2 测试 |
| log4j 格式 | Task 3 |
| 全量迁移 ~40 文件 | Task 4–6 |
| logging_config 不迁移 | Task 7 grep |
| 无新增环境变量 | 全计划无 config 变更 |
| 测试覆盖 | Task 1–3, 7 |

无 TBD / 「Similar to Task N」省略实现步骤之处。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-06-03-unified-log-tool.md`.

**两种执行方式：**

1. **Subagent-Driven（推荐）** — 每个 Task 派发独立 subagent，Task 间人工/Agent 复核，迭代快  
2. **Inline Execution** — 在本会话用 executing-plans 按 Task 批量执行，检查点暂停复核  

你想用哪种方式开始实现？
