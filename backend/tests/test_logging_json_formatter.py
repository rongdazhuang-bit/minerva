"""Tests for JSON log formatting."""

from __future__ import annotations

import json
import logging
import sys

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
            exc_info=sys.exc_info(),
        )

    data = _format_record(record)

    assert data["exception"]["type"] == "ValueError"
    assert data["exception"]["message"] == "bad"
    assert "ValueError: bad" in data["exception"]["traceback"]
