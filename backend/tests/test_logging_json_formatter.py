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


def test_json_formatter_preserves_non_ascii_message() -> None:
    """JSON logs keep non-ASCII messages readable."""

    record = logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        30,
        "你好 %s",
        ("世界",),
        None,
    )

    formatted = JsonLogFormatter().format(record)
    data = json.loads(formatted)

    assert "你好 世界" in formatted
    assert data["message"] == "你好 世界"


def test_json_formatter_ignores_empty_exception_tuple() -> None:
    """Empty exception tuples do not break formatting."""

    record = logging.LogRecord(
        "app.test",
        logging.ERROR,
        __file__,
        40,
        "failed",
        (),
        None,
    )
    record.exc_info = (None, None, None)

    data = _format_record(record)

    assert "exception" not in data


def test_json_formatter_protects_base_fields_and_context_from_extra() -> None:
    """Extra fields cannot overwrite formatter-owned fields."""

    with use_logging_context(request_id="req-1", process_type="api"):
        record = logging.LogRecord(
            "app.test",
            logging.INFO,
            __file__,
            50,
            "hello",
            (),
            None,
        )
        record.request_id = "extra-req"
        record.process_type = "worker"
        record.timestamp = "extra-time"
        record.level = "EXTRA"
        record.logger = "extra.logger"
        record.message = "extra-message"
        record.event = "test.event"

        data = _format_record(record)

    assert data["request_id"] == "req-1"
    assert data["process_type"] == "api"
    assert data["level"] == "INFO"
    assert data["logger"] == "app.test"
    assert data["message"] == "hello"
    assert data["event"] == "test.event"
    assert data["timestamp"] != "extra-time"


def test_json_formatter_stringifies_nested_non_json_extra() -> None:
    """Nested extra fields with non-JSON keys and values are stringified."""

    key = object()
    value = object()
    record = logging.LogRecord(
        "app.test",
        logging.INFO,
        __file__,
        60,
        "nested",
        (),
        None,
    )
    record.payload = {key: {"items": {value, "ok"}}}

    data = _format_record(record)

    nested_key = str(key)
    assert nested_key in data["payload"]
    assert str(value) in data["payload"][nested_key]["items"]
    assert "ok" in data["payload"][nested_key]["items"]
