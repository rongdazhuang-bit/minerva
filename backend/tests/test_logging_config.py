"""Tests for centralized logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import QueueHandler

from app.core.logging_config import configure_logging


def test_configure_logging_uses_queue_handler_for_async_sinks() -> None:
    """File and stdout sinks are drained by a background queue listener."""

    configure_logging(process_type="api", stdout_enabled=True, file_enabled=False)
    root = logging.getLogger()
    queue_handlers = [handler for handler in root.handlers if isinstance(handler, QueueHandler)]

    assert queue_handlers, "expected a QueueHandler on the root logger"
