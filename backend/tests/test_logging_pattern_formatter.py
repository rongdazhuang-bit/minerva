"""Tests for plain-text pattern log formatting."""

from __future__ import annotations

import logging
import sys

import pytest

from app.core.log import get_logger
from app.core.logging_context import use_logging_context
from app.core.logging_text import PatternLogFormatter, format_log_kv


def _format_line(record: logging.LogRecord) -> str:
    """Format one log record as a plain-text line."""

    return PatternLogFormatter().format(record)


def test_pattern_formatter_matches_expected_layout() -> None:
    """Pattern logs include timestamp, thread, chat id, trace id, level, logger, and message."""

    with use_logging_context(x_chat_id="chat-1", trace_id="trace-1", process_type="api"):
        record = logging.LogRecord(
            "app.agent.memory.mem0.logging_neo4j",
            logging.INFO,
            __file__,
            42,
            "mem0 neo4j request endpoint=neo4j://127.0.0.1:7687 db=neo4j cypher=RETURN 1",
            (),
            None,
        )
        line = _format_line(record)

    assert line.startswith("20")
    assert "[MainThread]" in line or "[" in line
    assert "[chat-1]" in line
    assert "trace-1" in line
    assert "INFO" in line
    assert "logging_neo4j:42 - mem0 neo4j request" in line


def test_pattern_formatter_appends_extra_fields_as_text() -> None:
    """Structured extras are appended as key=value text, not JSON."""

    record = logging.LogRecord(
        "app.http",
        logging.INFO,
        __file__,
        10,
        "http.request",
        (),
        None,
    )
    record.path = "/echo"
    record.status_code = 200

    line = _format_line(record)

    assert "http.request path=/echo status_code=200" in line
    assert "{" not in line


def test_pattern_formatter_serializes_exception() -> None:
    """Exception records append a traceback after the main line."""

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

    formatted = _format_line(record)

    assert "failed" in formatted.splitlines()[0]
    assert "ValueError: bad" in formatted


def test_format_log_kv_uses_plain_strings() -> None:
    """KV helper never emits JSON objects."""

    text = format_log_kv(
        endpoint="neo4j://127.0.0.1:7687",
        params={"user_id": "ws-1", "password": "secret"},
        rows=[{"name": "Alice"}],
    )

    assert "endpoint=neo4j://127.0.0.1:7687" in text
    assert "user_id=ws-1" in text
    assert "{" not in text or "{" in text and "user_id=ws-1" in text
    assert '"password"' not in text


def test_get_logger_output_matches_pattern_layout(caplog: pytest.LogCaptureFixture) -> None:
    """MinervaLogger records format to the log4j-style pattern layout."""

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
