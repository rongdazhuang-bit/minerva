"""Plain-text log formatting helpers and pattern formatter."""

from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import Any

from app.core.logging_context import get_logging_context

# Standard LogRecord attributes that should not be duplicated as extra fields.
_RESERVED_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys())
_RESERVED_RECORD_KEYS = _RESERVED_RECORD_KEYS | {"message", "asctime"}
# Formatter-owned and context fields that must not be repeated in trailing extras.
_EXTRA_RESERVED_KEYS = _RESERVED_RECORD_KEYS | frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "process_id",
        "thread_name",
        "module",
        "line",
        "exception",
        "request_id",
        "task_id",
        "process_type",
        "x_chat_id",
        "trace_id",
    }
)
_LOGGER_NAME_WIDTH = 50


def format_log_value(value: Any) -> str:
    """Format one log field value as a readable string (never JSON)."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        if any(char.isspace() for char in value) or "=" in value:
            return repr(value)
        return value
    if isinstance(value, dict):
        inner = ", ".join(f"{key}={format_log_value(item)}" for key, item in value.items())
        return f"{{{inner}}}"
    if isinstance(value, (list, tuple)):
        inner = ", ".join(format_log_value(item) for item in value)
        return f"[{inner}]"
    return repr(value)


def format_log_kv(**fields: Any) -> str:
    """Join keyword fields into ``key=value`` log text without JSON serialization."""

    parts: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={format_log_value(value)}")
    return " ".join(parts)


def _truncate_logger_name(name: str, *, width: int = _LOGGER_NAME_WIDTH) -> str:
    """Trim logger names longer than the configured pattern width."""

    if len(name) <= width:
        return name
    return name[-width:]


class PatternLogFormatter(logging.Formatter):
    """Format log records as plain text matching the Minerva log pattern."""

    def format(self, record: logging.LogRecord) -> str:
        """Serialize one log record to one human-readable line."""

        context = get_logging_context()
        x_chat_id = context.get("x_chat_id", "")
        trace_id = context.get("trace_id") or context.get("request_id", "")
        timestamp = (
            datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
            + f".{int(record.msecs):03d}"
        )
        level = record.levelname.ljust(5)[:5]
        logger_name = _truncate_logger_name(record.name)
        message = record.getMessage()
        extras = self._extra_fields(record)
        if extras:
            message = f"{message} {extras}" if message else extras
        line = (
            f"{timestamp} [{record.threadName}] [{x_chat_id}] {trace_id} "
            f"{level} {logger_name}:{record.lineno} - {message}"
        )
        exc_info = record.exc_info
        if (
            isinstance(exc_info, tuple)
            and len(exc_info) >= 3
            and exc_info[0] is not None
            and exc_info[1] is not None
        ):
            line += "\n" + "".join(traceback.format_exception(*exc_info[:3]))
        return line

    def _extra_fields(self, record: logging.LogRecord) -> str:
        """Return application-provided extra fields as trailing ``key=value`` text."""

        fields = {
            key: value
            for key, value in record.__dict__.items()
            if key not in _EXTRA_RESERVED_KEYS and not key.startswith("_")
        }
        if not fields:
            return ""
        return format_log_kv(**fields)
