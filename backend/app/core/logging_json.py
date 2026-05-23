"""JSON formatter for application logs."""

from __future__ import annotations

import json
import logging
import os
import traceback
from datetime import datetime, timezone
from typing import Any

from app.core.logging_context import get_logging_context

# Standard LogRecord attributes that should not be duplicated as extra fields.
_RESERVED_RECORD_KEYS = frozenset(logging.makeLogRecord({}).__dict__.keys())
_RESERVED_RECORD_KEYS = _RESERVED_RECORD_KEYS | {"message", "asctime"}
# Formatter-owned payload fields that application extras must not overwrite.
_BASE_PAYLOAD_KEYS = frozenset(
    {
        "timestamp",
        "level",
        "logger",
        "message",
        "process_id",
        "thread_name",
        "module",
        "line",
        "exception",
    }
)
# Logging context field names that must keep their contextvars values.
_CONTEXT_PAYLOAD_KEYS = frozenset({"request_id", "task_id", "process_type"})
# All names reserved from direct extra field emission.
_EXTRA_RESERVED_KEYS = _RESERVED_RECORD_KEYS | _BASE_PAYLOAD_KEYS | _CONTEXT_PAYLOAD_KEYS


def _to_json_safe(value: Any) -> Any:
    """Return a recursively JSON-serializable representation of a value."""

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, dict):
        return {str(key): _to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | set):
        return [_to_json_safe(item) for item in value]
    return str(value)


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
        exc_info = record.exc_info
        if (
            isinstance(exc_info, tuple)
            and len(exc_info) >= 3
            and exc_info[0] is not None
            and exc_info[1] is not None
        ):
            payload["exception"] = {
                "type": getattr(exc_info[0], "__name__", str(exc_info[0])),
                "message": str(exc_info[1]),
                "traceback": "".join(traceback.format_exception(*exc_info[:3])),
            }
        return json.dumps(_to_json_safe(payload), ensure_ascii=False)

    def _extra_fields(self, record: logging.LogRecord) -> dict[str, Any]:
        """Return application-provided extra fields without stdlib internals."""

        return {
            key: _to_json_safe(value)
            for key, value in record.__dict__.items()
            if key not in _EXTRA_RESERVED_KEYS and not key.startswith("_")
        }
