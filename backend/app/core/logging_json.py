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
