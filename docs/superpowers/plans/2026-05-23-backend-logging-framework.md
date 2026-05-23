# Backend Logging Framework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend logging framework that emits JSON logs to stdout and 7-day rolling files, captures sanitized API request/response payloads, and carries `request_id` across FastAPI and Celery.

**Architecture:** Keep the existing stdlib `logging.getLogger(__name__)` pattern and add focused infrastructure modules under `backend/app/core/`. Context handling uses `contextvars`; JSON formatting, redaction, file/stdout handler setup, and HTTP body logging stay separated so each part is testable. FastAPI initializes logging before app construction, Celery initializes logging during app wiring and propagates request context through task headers.

**Tech Stack:** Python 3.11+, FastAPI, Starlette ASGI middleware, Celery, Pydantic Settings, stdlib `logging`, `TimedRotatingFileHandler`, pytest.

---

## File Structure

- Create `backend/app/core/logging_context.py`: contextvars for `request_id`, `task_id`, `process_type`, and helper context managers.
- Create `backend/app/core/logging_redaction.py`: recursive redaction, body parsing helpers, and truncation.
- Create `backend/app/core/logging_json.py`: JSON formatter and record serialization.
- Create `backend/app/core/logging_config.py`: idempotent logging setup, handler creation, log path resolution, Celery process type detection.
- Create `backend/app/core/logging_middleware.py`: ASGI middleware for request/response body logging and `X-Request-ID`.
- Modify `backend/app/config.py`: add logging Settings fields.
- Modify `backend/.env.example`: document logging env vars.
- Modify `backend/.env.dev`: add logging env vars for dev.
- Modify `.gitignore`: ignore `backend/logs/`.
- Modify `backend/app/main.py`: configure API logging and install middleware.
- Modify `backend/app/errors.py`: add structured exception logging and generic 500 handler.
- Modify `backend/app/celery_app.py`: configure worker/beat logging, inject `request_id` into enqueue headers, restore task context in workers.
- Modify selected long-flow modules only after framework tests pass:
  - `backend/app/core/infrastructure/db/bootstrap.py`
  - `backend/app/agent/infrastructure/langgraph_checkpointer.py`
  - `backend/app/agent/service/agent_graph_run_service.py`
  - `backend/app/file_ocr/service/scan_init.py`
  - `backend/app/translate/service/run_pipeline.py`
  - `backend/app/sys/celery/beat/minerva_scheduler.py`
- Create tests:
  - `backend/tests/test_logging_redaction.py`
  - `backend/tests/test_logging_json_formatter.py`
  - `backend/tests/test_logging_config.py`
  - `backend/tests/test_logging_middleware.py`
  - `backend/tests/test_celery_request_logging_context.py`

---

### Task 1: Logging Context

**Files:**
- Create: `backend/app/core/logging_context.py`
- Test: `backend/tests/test_logging_context.py`

- [ ] **Step 1: Write failing context tests**

Create `backend/tests/test_logging_context.py`:

```python
"""Tests for request/task logging context helpers."""

from app.core.logging_context import (
    clear_logging_context,
    get_logging_context,
    set_logging_context,
    use_logging_context,
)


def test_set_and_clear_logging_context() -> None:
    """Context fields are visible after set and removed after clear."""

    set_logging_context(request_id="req-1", task_id="task-1", process_type="api")

    assert get_logging_context() == {
        "request_id": "req-1",
        "task_id": "task-1",
        "process_type": "api",
    }

    clear_logging_context()

    assert get_logging_context() == {}


def test_use_logging_context_restores_previous_values() -> None:
    """Nested context usage restores the previous values after exit."""

    set_logging_context(request_id="outer", process_type="api")

    with use_logging_context(request_id="inner", task_id="task-2"):
        assert get_logging_context() == {
            "request_id": "inner",
            "task_id": "task-2",
            "process_type": "api",
        }

    assert get_logging_context() == {
        "request_id": "outer",
        "process_type": "api",
    }
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_logging_context.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.logging_context'`.

- [ ] **Step 3: Implement context helpers**

Create `backend/app/core/logging_context.py`:

```python
"""Request and task scoped logging context helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token

_request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)
_task_id_var: ContextVar[str | None] = ContextVar("task_id", default=None)
_process_type_var: ContextVar[str | None] = ContextVar("process_type", default=None)


def set_logging_context(
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    process_type: str | None = None,
) -> None:
    """Set non-empty logging context values for the current execution context."""

    if request_id is not None:
        _request_id_var.set(request_id)
    if task_id is not None:
        _task_id_var.set(task_id)
    if process_type is not None:
        _process_type_var.set(process_type)


def clear_logging_context() -> None:
    """Clear request and task scoped values for the current execution context."""

    _request_id_var.set(None)
    _task_id_var.set(None)
    _process_type_var.set(None)


def get_logging_context() -> dict[str, str]:
    """Return the currently active logging context without empty fields."""

    values = {
        "request_id": _request_id_var.get(),
        "task_id": _task_id_var.get(),
        "process_type": _process_type_var.get(),
    }
    return {key: value for key, value in values.items() if value}


@contextmanager
def use_logging_context(
    *,
    request_id: str | None = None,
    task_id: str | None = None,
    process_type: str | None = None,
) -> Iterator[None]:
    """Temporarily apply logging context and restore previous values on exit."""

    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    if request_id is not None:
        tokens.append((_request_id_var, _request_id_var.set(request_id)))
    if task_id is not None:
        tokens.append((_task_id_var, _task_id_var.set(task_id)))
    if process_type is not None:
        tokens.append((_process_type_var, _process_type_var.set(process_type)))
    try:
        yield
    finally:
        for var, token in reversed(tokens):
            var.reset(token)
```

- [ ] **Step 4: Run test and verify it passes**

Run: `cd backend; python -m pytest tests/test_logging_context.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logging_context.py backend/tests/test_logging_context.py
git commit -m "feat(logging): add scoped logging context"
```

---

### Task 2: Redaction And Truncation

**Files:**
- Create: `backend/app/core/logging_redaction.py`
- Test: `backend/tests/test_logging_redaction.py`

- [ ] **Step 1: Write failing redaction tests**

Create `backend/tests/test_logging_redaction.py`:

```python
"""Tests for log payload redaction and truncation."""

from app.core.logging_redaction import redact_for_log


def test_redact_for_log_masks_nested_sensitive_values() -> None:
    """Sensitive keys are masked recursively and case-insensitively."""

    payload = {
        "Authorization": "Bearer secret",
        "user": {
            "password": "pw",
            "items": [{"api_key": "key"}, {"name": "safe"}],
        },
    }

    assert redact_for_log(payload, max_chars=1000) == {
        "Authorization": "[REDACTED]",
        "user": {
            "password": "[REDACTED]",
            "items": [{"api_key": "[REDACTED]"}, {"name": "safe"}],
        },
    }


def test_redact_for_log_truncates_long_strings() -> None:
    """Long strings are shortened and include the original length."""

    result = redact_for_log({"body": "abcdef"}, max_chars=3)

    assert result == {
        "body": {
            "truncated": True,
            "original_length": 6,
            "value": "abc",
        }
    }


def test_redact_for_log_handles_binary_values() -> None:
    """Bytes are summarized instead of being logged raw."""

    result = redact_for_log({"file": b"abc"}, max_chars=100)

    assert result == {"file": {"binary": True, "length": 3}}
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_logging_redaction.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.logging_redaction'`.

- [ ] **Step 3: Implement redaction helpers**

Create `backend/app/core/logging_redaction.py`:

```python
"""Sanitize values before they are written to application logs."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

SENSITIVE_FIELD_NAMES = frozenset(
    {
        "password",
        "token",
        "access_token",
        "refresh_token",
        "authorization",
        "api_key",
        "secret",
        "jwt",
        "captcha",
        "credential",
        "cookie",
        "set-cookie",
    }
)


def _is_sensitive_key(key: object) -> bool:
    """Return whether a mapping key should have its value masked."""

    return str(key).strip().lower() in SENSITIVE_FIELD_NAMES


def _truncate_text(value: str, max_chars: int) -> str | dict[str, Any]:
    """Return text unchanged or a structured truncation summary."""

    if len(value) <= max_chars:
        return value
    return {
        "truncated": True,
        "original_length": len(value),
        "value": value[:max_chars],
    }


def redact_for_log(value: Any, *, max_chars: int) -> Any:
    """Recursively redact sensitive values and truncate oversized payloads."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if _is_sensitive_key(key)
            else redact_for_log(item, max_chars=max_chars)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_log(item, max_chars=max_chars) for item in value]
    if isinstance(value, tuple):
        return [redact_for_log(item, max_chars=max_chars) for item in value]
    if isinstance(value, bytes):
        return {"binary": True, "length": len(value)}
    if isinstance(value, str):
        return _truncate_text(value, max_chars)
    return value
```

- [ ] **Step 4: Run test and verify it passes**

Run: `cd backend; python -m pytest tests/test_logging_redaction.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logging_redaction.py backend/tests/test_logging_redaction.py
git commit -m "feat(logging): add log redaction helpers"
```

---

### Task 3: JSON Formatter

**Files:**
- Create: `backend/app/core/logging_json.py`
- Test: `backend/tests/test_logging_json_formatter.py`

- [ ] **Step 1: Write failing formatter tests**

Create `backend/tests/test_logging_json_formatter.py`:

```python
"""Tests for JSON log formatting."""

from __future__ import annotations

import json
import logging

from app.core.logging_context import use_logging_context
from app.core.logging_json import JsonLogFormatter


def _format_record(record: logging.LogRecord) -> dict:
    """Format one log record and parse the JSON output."""

    return json.loads(JsonLogFormatter().format(record))


def test_json_formatter_includes_base_fields_and_context() -> None:
    """JSON logs include core record fields and contextvars."""

    with use_logging_context(request_id="req-1", process_type="api"):
        record = logging.LogRecord(
            "app.test",
            logging.INFO,
            __file__,
            12,
            "hello %s",
            ("world",),
            None,
        )
        record.event = "test.event"

        data = _format_record(record)

    assert data["level"] == "INFO"
    assert data["logger"] == "app.test"
    assert data["message"] == "hello world"
    assert data["event"] == "test.event"
    assert data["request_id"] == "req-1"
    assert data["process_type"] == "api"
    assert data["line"] == 12


def test_json_formatter_serializes_exception() -> None:
    """Exception records include structured exception information."""

    try:
        raise ValueError("bad")
    except ValueError:
        record = logging.getLogger("app.test").makeRecord(
            "app.test",
            logging.ERROR,
            __file__,
            20,
            "failed",
            (),
            exc_info=True,
        )

    data = _format_record(record)

    assert data["exception"]["type"] == "ValueError"
    assert data["exception"]["message"] == "bad"
    assert "ValueError: bad" in data["exception"]["traceback"]
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_logging_json_formatter.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.logging_json'`.

- [ ] **Step 3: Implement JSON formatter**

Create `backend/app/core/logging_json.py`:

```python
"""JSON formatter for application logs."""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any

from app.core.logging_context import get_logging_context

_RESERVED_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys())
_RESERVED_RECORD_KEYS = _RESERVED_RECORD_KEYS | {"message", "asctime"}


class JsonLogFormatter(logging.Formatter):
    """Format log records as one JSON object per line."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize one log record to a JSON string."""

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "process_id": os.getpid(),
            "thread_name": record.threadName,
            "module": record.module,
            "line": record.lineno,
        }
        payload.update(get_logging_context())
        payload.update(self._extra_fields(record))
        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": "".join(traceback.format_exception(*record.exc_info)),
            }
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _extra_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        """Return application-provided extra fields without stdlib internals."""

        return {
            key: value
            for key, value in record.__dict__.items()
            if key not in _RESERVED_RECORD_KEYS and not key.startswith("_")
        }
```

- [ ] **Step 4: Run test and verify it passes**

Run: `cd backend; python -m pytest tests/test_logging_json_formatter.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logging_json.py backend/tests/test_logging_json_formatter.py
git commit -m "feat(logging): add json log formatter"
```

---

### Task 4: Settings, Env Files, And Gitignore

**Files:**
- Modify: `backend/app/config.py`
- Modify: `backend/.env.example`
- Modify: `backend/.env.dev`
- Modify: `.gitignore`
- Test: `backend/tests/test_logging_settings.py`

- [ ] **Step 1: Write failing settings tests**

Create `backend/tests/test_logging_settings.py`:

```python
"""Tests for logging settings defaults."""

from app.config import settings


def test_logging_settings_defaults() -> None:
    """Logging settings expose the configured default values."""

    assert settings.log_level == "INFO"
    assert settings.log_dir == "logs"
    assert settings.log_retention_days == 7
    assert settings.log_body_enabled is True
    assert settings.log_body_max_chars == 20000
    assert settings.log_file_enabled is True
    assert settings.log_stdout_enabled is True
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_logging_settings.py -v`

Expected: FAIL with `AttributeError` for missing logging settings.

- [ ] **Step 3: Add settings fields**

Modify `backend/app/config.py` inside `class Settings` after `app_env`:

```python
    log_level: str = Field(
        default="INFO",
        description="Application log level: DEBUG, INFO, WARNING, ERROR, or CRITICAL.",
        validation_alias=AliasChoices("LOG_LEVEL", "log_level"),
    )
    log_dir: str = Field(
        default="logs",
        description="Log directory relative to backend/ unless an absolute path is provided.",
        validation_alias=AliasChoices("LOG_DIR", "log_dir"),
    )
    log_retention_days: int = Field(
        default=7,
        ge=1,
        le=365,
        description="Number of daily log files to keep.",
        validation_alias=AliasChoices("LOG_RETENTION_DAYS", "log_retention_days"),
    )
    log_body_enabled: bool = Field(
        default=True,
        description="When True, HTTP middleware logs sanitized request and response bodies.",
        validation_alias=AliasChoices("LOG_BODY_ENABLED", "log_body_enabled"),
    )
    log_body_max_chars: int = Field(
        default=20000,
        ge=0,
        le=1_000_000,
        description="Maximum characters kept for one logged HTTP request or response body.",
        validation_alias=AliasChoices("LOG_BODY_MAX_CHARS", "log_body_max_chars"),
    )
    log_file_enabled: bool = Field(
        default=True,
        description="When True, application logs are written to rotating local log files.",
        validation_alias=AliasChoices("LOG_FILE_ENABLED", "log_file_enabled"),
    )
    log_stdout_enabled: bool = Field(
        default=True,
        description="When True, application logs are written to stdout.",
        validation_alias=AliasChoices("LOG_STDOUT_ENABLED", "log_stdout_enabled"),
    )
```

- [ ] **Step 4: Update env files**

Add this block to `backend/.env.example` after `APP_NAME=minerva-api`:

```dotenv
# -----------------------------------------------------------------------------
# 日志
# -----------------------------------------------------------------------------
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_RETENTION_DAYS=7
LOG_BODY_ENABLED=true
LOG_BODY_MAX_CHARS=20000
LOG_FILE_ENABLED=true
LOG_STDOUT_ENABLED=true
```

Add this block to `backend/.env.dev` after `APP_NAME=minerva-api`:

```dotenv
LOG_LEVEL=INFO
LOG_DIR=logs
LOG_RETENTION_DAYS=7
LOG_BODY_ENABLED=true
LOG_BODY_MAX_CHARS=20000
LOG_FILE_ENABLED=true
LOG_STDOUT_ENABLED=true
```

- [ ] **Step 5: Ignore backend logs**

Add to `.gitignore` near existing backend ignores:

```gitignore
/backend/logs/
```

- [ ] **Step 6: Run test and verify it passes**

Run: `cd backend; python -m pytest tests/test_logging_settings.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add .gitignore backend/app/config.py backend/.env.example backend/.env.dev backend/tests/test_logging_settings.py
git commit -m "feat(logging): add logging settings"
```

---

### Task 5: Logging Configuration

**Files:**
- Create: `backend/app/core/logging_config.py`
- Test: `backend/tests/test_logging_config.py`

- [ ] **Step 1: Write failing configuration tests**

Create `backend/tests/test_logging_config.py`:

```python
"""Tests for logging handler configuration."""

from __future__ import annotations

import logging
from logging.handlers import TimedRotatingFileHandler

from app.core.logging_config import configure_logging, resolve_log_file_path


def test_resolve_log_file_path_uses_process_type(tmp_path) -> None:
    """Process type selects the correct log file name."""

    assert resolve_log_file_path("api", tmp_path).name == "api.log"
    assert resolve_log_file_path("worker", tmp_path).name == "worker.log"
    assert resolve_log_file_path("beat", tmp_path).name == "beat.log"


def test_configure_logging_is_idempotent(tmp_path) -> None:
    """Repeated configuration replaces managed handlers instead of duplicating them."""

    root = logging.getLogger()
    configure_logging(
        process_type="api",
        log_dir=tmp_path,
        level_name="INFO",
        retention_days=7,
        stdout_enabled=False,
        file_enabled=True,
    )
    configure_logging(
        process_type="api",
        log_dir=tmp_path,
        level_name="INFO",
        retention_days=7,
        stdout_enabled=False,
        file_enabled=True,
    )

    managed = [handler for handler in root.handlers if getattr(handler, "_minerva_logging", False)]

    assert len(managed) == 1
    assert isinstance(managed[0], TimedRotatingFileHandler)
    assert managed[0].backupCount == 7
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_logging_config.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.logging_config'`.

- [ ] **Step 3: Implement logging configuration**

Create `backend/app/core/logging_config.py`:

```python
"""Central logging setup for API, Celery worker, and Celery beat processes."""

from __future__ import annotations

import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path

from app.config import settings
from app.core.logging_context import set_logging_context
from app.core.logging_json import JsonLogFormatter

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_PROCESS_LOG_FILES = {
    "api": "api.log",
    "worker": "worker.log",
    "beat": "beat.log",
}


def normalize_log_level(level_name: str) -> int:
    """Convert a configured level name into a stdlib logging level."""

    normalized = level_name.strip().upper()
    if normalized not in _VALID_LEVELS:
        raise ValueError(f"Invalid LOG_LEVEL: {level_name}")
    return getattr(logging, normalized)


def resolve_log_dir(raw_log_dir: str | Path | None = None) -> Path:
    """Resolve the configured log directory relative to backend/ when needed."""

    raw = Path(raw_log_dir or settings.log_dir)
    if raw.is_absolute():
        return raw
    backend_dir = Path(__file__).resolve().parents[2]
    return backend_dir / raw


def resolve_log_file_path(process_type: str, log_dir: str | Path | None = None) -> Path:
    """Return the rolling log file path for one backend process type."""

    file_name = _PROCESS_LOG_FILES.get(process_type, f"{process_type}.log")
    return resolve_log_dir(log_dir) / file_name


def _remove_managed_handlers(root: logging.Logger) -> None:
    """Detach and close handlers previously installed by this module."""

    for handler in list(root.handlers):
        if getattr(handler, "_minerva_logging", False):
            root.removeHandler(handler)
            handler.close()


def _mark_managed(handler: logging.Handler) -> logging.Handler:
    """Mark one handler as owned by the Minerva logging configuration."""

    handler._minerva_logging = True  # type: ignore[attr-defined]
    handler.setFormatter(JsonLogFormatter())
    return handler


def configure_logging(
    *,
    process_type: str,
    log_dir: str | Path | None = None,
    level_name: str | None = None,
    retention_days: int | None = None,
    stdout_enabled: bool | None = None,
    file_enabled: bool | None = None,
) -> None:
    """Configure root and common third-party loggers for one backend process."""

    level = normalize_log_level(level_name or settings.log_level)
    root = logging.getLogger()
    root.setLevel(level)
    _remove_managed_handlers(root)

    enable_stdout = settings.log_stdout_enabled if stdout_enabled is None else stdout_enabled
    enable_file = settings.log_file_enabled if file_enabled is None else file_enabled

    if enable_stdout:
        stream_handler = _mark_managed(logging.StreamHandler(sys.stdout))
        stream_handler.setLevel(level)
        root.addHandler(stream_handler)

    if enable_file:
        path = resolve_log_file_path(process_type, log_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = TimedRotatingFileHandler(
            filename=path,
            when="midnight",
            backupCount=retention_days or settings.log_retention_days,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        root.addHandler(_mark_managed(file_handler))

    for logger_name in ("uvicorn", "uvicorn.error", "celery"):
        logging.getLogger(logger_name).setLevel(level)
    logging.getLogger("uvicorn.access").propagate = True
    set_logging_context(process_type=process_type)
```

- [ ] **Step 4: Run test and verify it passes**

Run: `cd backend; python -m pytest tests/test_logging_config.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logging_config.py backend/tests/test_logging_config.py
git commit -m "feat(logging): configure json log handlers"
```

---

### Task 6: API Request And Response Logging Middleware

**Files:**
- Create: `backend/app/core/logging_middleware.py`
- Test: `backend/tests/test_logging_middleware.py`

- [ ] **Step 1: Write failing middleware tests**

Create `backend/tests/test_logging_middleware.py`:

```python
"""Tests for HTTP request and response logging middleware."""

from __future__ import annotations

import json
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.testclient import TestClient

from app.core.logging_middleware import HttpLoggingMiddleware


def _build_app() -> FastAPI:
    """Create a minimal FastAPI app using the HTTP logging middleware."""

    app = FastAPI()
    app.add_middleware(HttpLoggingMiddleware, body_max_chars=1000, body_enabled=True)

    @app.post("/echo")
    async def echo(request: Request) -> JSONResponse:
        body = await request.json()
        return JSONResponse({"received": body, "token": "response-secret"})

    @app.get("/stream")
    async def stream() -> StreamingResponse:
        return StreamingResponse(iter([b"hello"]), media_type="text/plain")

    return app


def test_http_logging_middleware_logs_sanitized_bodies(caplog) -> None:
    """Middleware logs request and response bodies without breaking endpoint reads."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.post("/echo", json={"password": "pw", "name": "alice"})

    assert response.status_code == 200
    assert response.headers["x-request-id"]
    assert response.json()["received"] == {"password": "pw", "name": "alice"}

    messages = [json.loads(record.getMessage()) for record in caplog.records if record.name == "app.http"]

    assert any(message["event"] == "http.request" for message in messages)
    assert any(message["event"] == "http.response" for message in messages)
    request_log = next(message for message in messages if message["event"] == "http.request")
    response_log = next(message for message in messages if message["event"] == "http.response")
    assert request_log["request_body"]["password"] == "[REDACTED]"
    assert response_log["response_body"]["token"] == "[REDACTED]"


def test_http_logging_middleware_does_not_consume_streams(caplog) -> None:
    """Streaming responses are returned intact and logged as summaries."""

    caplog.set_level(logging.INFO)
    client = TestClient(_build_app())

    response = client.get("/stream")

    assert response.status_code == 200
    assert response.text == "hello"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_logging_middleware.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'app.core.logging_middleware'`.

- [ ] **Step 3: Implement middleware**

Create `backend/app/core/logging_middleware.py`:

```python
"""HTTP middleware that logs sanitized request and response payloads."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import settings
from app.core.logging_context import use_logging_context
from app.core.logging_redaction import redact_for_log

_HTTP_LOGGER = logging.getLogger("app.http")
_STREAMING_TYPES = ("text/event-stream",)


def _parse_body(raw: bytes, headers: Headers, *, max_chars: int) -> Any:
    """Parse a request or response body into a safe log value."""

    content_type = headers.get("content-type", "")
    if not raw:
        return None
    if "multipart/form-data" in content_type:
        return {"multipart": True, "length": len(raw)}
    if "application/json" in content_type:
        try:
            return redact_for_log(json.loads(raw.decode("utf-8")), max_chars=max_chars)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return {"unparseable_json": True, "length": len(raw)}
    if content_type.startswith("text/"):
        return redact_for_log(raw.decode("utf-8", errors="replace"), max_chars=max_chars)
    return {"binary": True, "length": len(raw), "content_type": content_type}


def _safe_headers(headers: Headers, *, max_chars: int) -> dict[str, Any]:
    """Return sanitized request or response headers."""

    return redact_for_log(dict(headers.items()), max_chars=max_chars)


class HttpLoggingMiddleware:
    """Log HTTP request and response metadata plus sanitized payloads."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        body_enabled: bool | None = None,
        body_max_chars: int | None = None,
    ) -> None:
        """Initialize middleware with optional test overrides."""

        self.app = app
        self.body_enabled = settings.log_body_enabled if body_enabled is None else body_enabled
        self.body_max_chars = body_max_chars or settings.log_body_max_chars

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Handle one ASGI request and emit request/response logs."""

        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
        started = time.perf_counter()
        raw_body = await request.body()
        request_headers = Headers(scope=scope)

        async def replay_receive() -> Message:
            """Replay the already-read request body for downstream handlers."""

            return {"type": "http.request", "body": raw_body, "more_body": False}

        with use_logging_context(request_id=request_id):
            if self.body_enabled:
                _HTTP_LOGGER.info(
                    json.dumps(
                        {
                            "event": "http.request",
                            "request_id": request_id,
                            "method": request.method,
                            "path": request.url.path,
                            "query": redact_for_log(dict(request.query_params), max_chars=self.body_max_chars),
                            "client_ip": request.client.host if request.client else None,
                            "headers": _safe_headers(request_headers, max_chars=self.body_max_chars),
                            "content_type": request_headers.get("content-type"),
                            "request_body": _parse_body(raw_body, request_headers, max_chars=self.body_max_chars),
                        },
                        ensure_ascii=False,
                    ),
                    extra={"event": "http.request"},
                )
            await self._send_with_response_logging(
                scope,
                replay_receive,
                send,
                request_id=request_id,
                started=started,
            )

    async def _send_with_response_logging(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
        *,
        request_id: str,
        started: float,
    ) -> None:
        """Wrap ASGI send to capture non-streaming response bodies."""

        status_code = 500
        response_headers: list[tuple[bytes, bytes]] = []
        body_parts: list[bytes] = []

        async def wrapped_send(message: Message) -> None:
            """Capture response metadata and forward each ASGI message."""

            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                response_headers = list(message.get("headers", []))
                response_headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": response_headers}
            elif message["type"] == "http.response.body":
                body = message.get("body", b"")
                if body and not message.get("more_body", False):
                    body_parts.append(body)
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            headers = Headers(raw=response_headers)
            content_type = headers.get("content-type", "")
            is_stream = content_type.startswith(_STREAMING_TYPES)
            response_body = {"streaming": True, "content_type": content_type} if is_stream else _parse_body(
                b"".join(body_parts),
                headers,
                max_chars=self.body_max_chars,
            )
            _HTTP_LOGGER.info(
                json.dumps(
                    {
                        "event": "http.response",
                        "request_id": request_id,
                        "method": scope["method"],
                        "path": scope["path"],
                        "status_code": status_code,
                        "duration_ms": duration_ms,
                        "content_type": content_type,
                        "response_body": response_body if self.body_enabled else None,
                    },
                    ensure_ascii=False,
                ),
                extra={"event": "http.response", "status_code": status_code},
            )
```

- [ ] **Step 4: Run middleware tests and adjust logging shape**

Run: `cd backend; python -m pytest tests/test_logging_middleware.py -v`

Expected: PASS. If caplog captures JSON formatter output instead of raw message, update tests to read `record.getMessage()` only for `record.name == "app.http"` and keep assertions on the embedded JSON payload.

- [ ] **Step 5: Commit**

```bash
git add backend/app/core/logging_middleware.py backend/tests/test_logging_middleware.py
git commit -m "feat(logging): log sanitized http payloads"
```

---

### Task 7: Wire FastAPI Logging And Exceptions

**Files:**
- Modify: `backend/app/main.py`
- Modify: `backend/app/errors.py`
- Test: `backend/tests/test_api_logging_integration.py`

- [ ] **Step 1: Write failing integration tests**

Create `backend/tests/test_api_logging_integration.py`:

```python
"""Integration tests for API logging wiring."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.errors import register_exception_handlers
from app.exceptions import AppError


def test_generic_exception_handler_returns_stable_500() -> None:
    """Unhandled exceptions are normalized instead of exposing stack traces."""

    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("secret detail")

    response = TestClient(app, raise_server_exceptions=False).get("/boom")

    assert response.status_code == 500
    assert response.json()["code"] == "internal.error"
    assert response.json()["message"] == "Internal server error"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_api_logging_integration.py -v`

Expected: FAIL because generic exceptions are not registered yet.

- [ ] **Step 3: Wire API logging**

Modify `backend/app/main.py` imports and app setup:

```python
from app.core.logging_config import configure_logging
from app.core.logging_middleware import HttpLoggingMiddleware

configure_logging(process_type="api")

app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(HttpLoggingMiddleware)
```

Place `configure_logging(process_type="api")` after imports and before `app = FastAPI(...)`. Place `app.add_middleware(HttpLoggingMiddleware)` before `app.include_router(api)`.

- [ ] **Step 4: Add exception logging**

Modify `backend/app/errors.py`:

```python
import logging

from app.core.logging_context import get_logging_context

logger = logging.getLogger(__name__)
```

Inside `app_error_handler` before returning:

```python
        logger.warning(
            "application error",
            extra={
                "event": "http.error",
                "request_id": get_logging_context().get("request_id"),
                "path": str(_request.url.path),
                "code": exc.code,
                "status_code": exc.status_code,
            },
        )
```

Rename `_request` to `request` in the handler signature.

Inside `validation_handler` before returning:

```python
        logger.warning(
            "request validation error",
            extra={
                "event": "http.error",
                "request_id": get_logging_context().get("request_id"),
                "path": str(request.url.path),
                "code": "request.validation",
                "status_code": 422,
            },
        )
```

Add a generic handler at the end of `register_exception_handlers()`:

```python
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        """Return a stable 500 body while logging the original exception."""

        logger.exception(
            "unhandled request error",
            extra={
                "event": "http.error",
                "request_id": get_logging_context().get("request_id"),
                "path": str(request.url.path),
                "code": "internal.error",
                "status_code": 500,
            },
        )
        return JSONResponse(
            status_code=500,
            content=ErrorBody(
                code="internal.error",
                message="Internal server error",
                type="http",
                details=None,
            ).model_dump(mode="json"),
        )
```

- [ ] **Step 5: Run integration tests**

Run: `cd backend; python -m pytest tests/test_api_logging_integration.py tests/test_logging_middleware.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/app/main.py backend/app/errors.py backend/tests/test_api_logging_integration.py
git commit -m "feat(logging): wire api logging"
```

---

### Task 8: Celery Request ID Propagation

**Files:**
- Modify: `backend/app/celery_app.py`
- Test: `backend/tests/test_celery_request_logging_context.py`

- [ ] **Step 1: Write failing Celery context tests**

Create `backend/tests/test_celery_request_logging_context.py`:

```python
"""Tests for Celery request_id propagation into task logging context."""

from app.celery_app import _merge_request_id_header
from app.core.logging_context import get_logging_context, use_logging_context


def test_merge_request_id_header_uses_context_when_missing() -> None:
    """Current request_id is injected into Celery headers when absent."""

    with use_logging_context(request_id="req-1"):
        headers = _merge_request_id_header({"existing": "value"})

    assert headers == {"existing": "value", "request_id": "req-1"}


def test_merge_request_id_header_preserves_explicit_value() -> None:
    """Explicit Celery request_id header wins over context."""

    with use_logging_context(request_id="req-context"):
        headers = _merge_request_id_header({"request_id": "req-explicit"})

    assert headers["request_id"] == "req-explicit"
```

- [ ] **Step 2: Run test and verify it fails**

Run: `cd backend; python -m pytest tests/test_celery_request_logging_context.py -v`

Expected: FAIL with missing `_merge_request_id_header`.

- [ ] **Step 3: Configure Celery logging and header merge**

Modify `backend/app/celery_app.py` imports:

```python
import logging

from app.core.logging_config import configure_logging
from app.core.logging_context import clear_logging_context, get_logging_context, set_logging_context
```

Add near constants:

```python
logger = logging.getLogger(__name__)
```

Add helper:

```python
def _resolve_celery_process_type() -> str:
    """Resolve whether the current Celery process is beat or worker."""

    argv = " ".join(sys.argv).lower()
    if " beat" in f" {argv} ":
        return "beat"
    return "worker"


def _merge_request_id_header(headers: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return Celery headers with current request_id when the caller did not provide one."""

    merged = dict(headers or {})
    context_request_id = get_logging_context().get("request_id")
    if context_request_id and "request_id" not in merged:
        merged["request_id"] = context_request_id
    return merged or None
```

Call logging configuration before `celery_app = _build_celery_app()`:

```python
configure_logging(process_type=_resolve_celery_process_type())
```

Modify `enqueue_task()`:

```python
        result = celery_app.send_task(
            task_name,
            args=args or [],
            kwargs=kwargs or {},
            headers=_merge_request_id_header(headers),
            queue=settings.celery_default_queue,
        )
        logger.info(
            "celery task enqueued",
            extra={
                "event": "celery.task.enqueued",
                "task_name": task_name,
                "task_id": str(result.id),
                "queue": settings.celery_default_queue,
            },
        )
```

Inside the `if celery_app is not None:` block, import signals:

```python
        from celery.signals import task_postrun, task_prerun, task_retry
```

Add signal handlers:

```python
        def _set_task_logging_context(task=None, task_id=None, **kwargs) -> None:
            """Restore request_id and task_id before Celery task execution."""

            request = getattr(task, "request", None)
            headers = getattr(request, "headers", None) or {}
            request_id = headers.get("request_id")
            task_name = getattr(task, "name", None)
            set_logging_context(request_id=request_id, task_id=str(task_id) if task_id else None)
            logger.info(
                "celery task started",
                extra={
                    "event": "celery.task.started",
                    "task_name": task_name,
                    "task_id": str(task_id) if task_id else None,
                },
            )

        def _clear_task_logging_context(task=None, task_id=None, state=None, **kwargs) -> None:
            """Log Celery task completion and clear task-scoped context."""

            logger.info(
                "celery task finished",
                extra={
                    "event": "celery.task.finished",
                    "task_name": getattr(task, "name", None),
                    "task_id": str(task_id) if task_id else None,
                    "state": state,
                },
            )
            clear_logging_context()

        task_prerun.connect(_set_task_logging_context, weak=False)
        task_postrun.connect(_clear_task_logging_context, weak=False)
```

- [ ] **Step 4: Run Celery tests**

Run: `cd backend; python -m pytest tests/test_celery_request_logging_context.py -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/celery_app.py backend/tests/test_celery_request_logging_context.py
git commit -m "feat(logging): propagate request id to celery"
```

---

### Task 9: Boundary Log Points

**Files:**
- Modify: `backend/app/core/infrastructure/db/bootstrap.py`
- Modify: `backend/app/agent/infrastructure/langgraph_checkpointer.py`
- Modify: `backend/app/agent/service/agent_graph_run_service.py`
- Modify: `backend/app/file_ocr/service/scan_init.py`
- Modify: `backend/app/translate/service/run_pipeline.py`
- Modify: `backend/app/sys/celery/beat/minerva_scheduler.py`
- Test: existing module tests plus lint

- [ ] **Step 1: Add database bootstrap logs**

`backend/app/core/infrastructure/db/bootstrap.py` already has `logger`. Replace `create_missing_tables()` with this version so start, skip, success, and failure all emit structured events:

```python
async def create_missing_tables() -> None:
    """Create missing ORM tables when enabled by settings."""

    if not settings.auto_create_tables:
        logger.info("database bootstrap skipped", extra={"event": "db.bootstrap.skipped"})
        return
    _import_models()
    from app.core.infrastructure.db.session import engine

    logger.info("database bootstrap started", extra={"event": "db.bootstrap.started"})
    try:
        async with engine.begin() as conn:
            await conn.run_sync(
                Base.metadata.create_all,
                checkfirst=True,
            )
    except Exception as e:
        if not (_dev_like_env() and _is_db_unavailable(e)):
            logger.exception("database bootstrap failed", extra={"event": "db.bootstrap.failed"})
            raise
        logger.warning(
            "无法连接 PostgreSQL，开发环境已跳过启动建表（AUTO_CREATE_TABLES 仍为真）。"
            "请启动数据库后重启，或先设置 AUTO_CREATE_TABLES=false；业务接口仍需要可用的数据库。",
            extra={"event": "db.bootstrap.skipped_unavailable"},
        )
        logger.debug("跳过建表原因", exc_info=e)
        return
    logger.info("database bootstrap finished", extra={"event": "db.bootstrap.finished"})
```

- [ ] **Step 2: Add LangGraph checkpoint logs**

In `backend/app/agent/infrastructure/langgraph_checkpointer.py`, add or reuse logger:

```python
logger = logging.getLogger(__name__)
```

Log initialization and close:

```python
logger.info("langgraph checkpointer initializing", extra={"event": "agent.checkpointer.init"})
logger.info("langgraph checkpointer closed", extra={"event": "agent.checkpointer.closed"})
logger.exception("langgraph checkpointer failed", extra={"event": "agent.checkpointer.failed"})
```

- [ ] **Step 3: Add Agent run boundary fields**

In `backend/app/agent/service/agent_graph_run_service.py`, keep existing logs and ensure key run logs include:

```python
extra={
    "event": "agent.run.failed",
    "run_id": str(run_id),
    "session_id": str(session_id),
}
```

Also add start/finish info logs if not present:

```python
logger.info("agent run started", extra={"event": "agent.run.started", "run_id": str(run_id)})
logger.info("agent run finished", extra={"event": "agent.run.finished", "run_id": str(run_id)})
```

- [ ] **Step 4: Add OCR and translate summaries**

In `backend/app/file_ocr/service/scan_init.py`, add summary logs:

```python
logger.info(
    "ocr scan initialized",
    extra={
        "event": "ocr.scan.initialized",
        "task_id": str(task_id),
        "file_count": file_count,
    },
)
```

In `backend/app/translate/service/run_pipeline.py`, add:

```python
logger.info(
    "translate pipeline started",
    extra={"event": "translate.pipeline.started", "task_id": str(task_id)},
)
logger.info(
    "translate pipeline finished",
    extra={"event": "translate.pipeline.finished", "task_id": str(task_id)},
)
```

- [ ] **Step 5: Add Beat scheduler logs**

In `backend/app/sys/celery/beat/minerva_scheduler.py`, ensure reload/reconcile logs include:

```python
extra={
    "event": "celery.beat.reconcile",
    "job_count": len(rows),
}
```

- [ ] **Step 6: Run focused regression tests**

Run:

```bash
cd backend
python -m pytest tests -v
```

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/infrastructure/db/bootstrap.py backend/app/agent/infrastructure/langgraph_checkpointer.py backend/app/agent/service/agent_graph_run_service.py backend/app/file_ocr/service/scan_init.py backend/app/translate/service/run_pipeline.py backend/app/sys/celery/beat/minerva_scheduler.py
git commit -m "feat(logging): add boundary diagnostics"
```

---

### Task 10: Spec Backfill And Full Verification

**Files:**
- Modify: `docs/superpowers/specs/2026-05-23-backend-logging-framework-design.md`

- [ ] **Step 1: Add implementation comparison section**

Append to `docs/superpowers/specs/2026-05-23-backend-logging-framework-design.md`:

```markdown
---

## 16. 实现对照（以代码为准，2026-05-23）

| Spec 条目 | 当前代码位置 | 备注 |
| --- | --- | --- |
| JSON 日志 formatter | `backend/app/core/logging_json.py` | 每行一条 JSON，合并 context 与 `extra`。 |
| 脱敏与截断 | `backend/app/core/logging_redaction.py` | 敏感字段递归脱敏，长文本截断。 |
| 日志初始化与滚动文件 | `backend/app/core/logging_config.py` | stdout + `TimedRotatingFileHandler`，按进程文件。 |
| API 请求/响应报文日志 | `backend/app/core/logging_middleware.py` | 记录 request/response 摘要，返回 `X-Request-ID`。 |
| FastAPI 接入 | `backend/app/main.py`、`backend/app/errors.py` | 初始化日志、中间件、异常日志。 |
| Celery request_id 贯穿 | `backend/app/celery_app.py` | 入队 headers 注入，任务侧恢复上下文。 |
| 关键边界日志 | Agent/OCR/Translate/Beat/DB 相关模块 | 记录开始、结束、失败摘要。 |
```

- [ ] **Step 2: Run full verification**

Run:

```bash
cd backend
python -m pytest tests -v
python -m ruff check .
```

Expected: both commands PASS.

- [ ] **Step 3: Verify git diff is scoped**

Run:

```bash
git status --short
git diff --stat
```

Expected: only logging framework implementation, tests, env docs, `.gitignore`, and spec backfill files are changed.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-05-23-backend-logging-framework-design.md
git commit -m "docs(logging): backfill implementation notes"
```

---

## Self-Review

- Spec coverage: the plan covers JSON logging, stdout/file output, 7-day rolling files, API request/response body logs, redaction/truncation, `X-Request-ID`, Celery propagation, key boundary logs, env sync, tests, and spec backfill.
- Placeholder scan: no marker placeholders or unspecified implementation steps remain.
- Type consistency: module names use `app.core.logging_*`; process types are `api`, `worker`, `beat`; request header is `request_id` inside Celery headers and `X-Request-ID` for HTTP.
- Scope check: the plan stays within backend API, Celery Worker, and Celery Beat. Frontend logging, database audit logs, and broad CRUD debug logs remain out of scope.
