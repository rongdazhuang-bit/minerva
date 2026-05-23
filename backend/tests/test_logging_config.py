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
