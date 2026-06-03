"""Tests for centralized logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import QueueHandler

from app.core.logging_config import configure_logging
from app.core.logging_text import PatternLogFormatter


def test_configure_logging_uses_pattern_formatter() -> None:
    """Managed handlers use the plain-text pattern formatter."""

    import app.core.logging_config as logging_config_module

    configure_logging(process_type="api", stdout_enabled=True, file_enabled=False)
    listener = logging_config_module._queue_listener
    assert listener is not None
    assert isinstance(listener.handlers[0].formatter, PatternLogFormatter)


def test_configure_logging_uses_queue_handler_for_async_sinks() -> None:
    """File and stdout sinks are drained by a background queue listener."""

    configure_logging(process_type="api", stdout_enabled=True, file_enabled=False)
    root = logging.getLogger()
    queue_handlers = [handler for handler in root.handlers if isinstance(handler, QueueHandler)]

    assert queue_handlers, "expected a QueueHandler on the root logger"


def test_configure_logging_suppresses_watchfiles_info() -> None:
    """Uvicorn reload file-watcher logs should not flood application output."""

    configure_logging(process_type="api", stdout_enabled=True, file_enabled=False)

    assert logging.getLogger("watchfiles").level == logging.WARNING
    assert logging.getLogger("watchfiles.main").isEnabledFor(logging.INFO) is False


def test_configure_logging_suppresses_database_query_info() -> None:
    """SQLAlchemy and DB driver INFO logs should not appear in application output."""

    configure_logging(
        process_type="api",
        stdout_enabled=True,
        file_enabled=False,
        level_name="DEBUG",
    )

    assert logging.getLogger("sqlalchemy.engine").level == logging.WARNING
    assert logging.getLogger("sqlalchemy.engine").isEnabledFor(logging.INFO) is False
    assert logging.getLogger("psycopg.pool").level == logging.WARNING
