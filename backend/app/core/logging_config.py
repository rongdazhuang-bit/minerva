"""Central logging setup for API, Celery worker, and Celery beat processes."""

from __future__ import annotations

import atexit
import logging
import queue
import sys
from logging.handlers import QueueHandler, QueueListener
from pathlib import Path

from app.config import settings
from app.core.logging_context import set_logging_context
from app.core.logging_handlers import WindowsSafeTimedRotatingFileHandler
from app.core.logging_text import PatternLogFormatter

_VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
_PROCESS_LOG_FILES = {
    "api": "api.log",
    "worker": "worker.log",
    "beat": "beat.log",
}
# ORM/driver SQL and pool chatter stay off unless WARNING+.
_QUIET_DATABASE_LOGGERS = (
    "sqlalchemy",
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "sqlalchemy.orm",
    "sqlalchemy.dialects",
    "psycopg",
    "psycopg2",
    "psycopg.pool",
    "asyncpg",
    "alembic",
)
_queue_listener: QueueListener | None = None
_atexit_registered = False


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


def _stop_queue_listener() -> None:
    """Stop the background listener that drains the logging queue."""

    global _queue_listener
    if _queue_listener is not None:
        _queue_listener.stop()
        _queue_listener = None


def _remove_managed_handlers(root: logging.Logger) -> None:
    """Detach and close handlers previously installed by this module."""

    _stop_queue_listener()
    for handler in list(root.handlers):
        if getattr(handler, "_minerva_logging", False):
            root.removeHandler(handler)
            handler.close()


def _mark_managed(handler: logging.Handler) -> logging.Handler:
    """Mark one handler as owned by the Minerva logging configuration."""

    handler._minerva_logging = True  # type: ignore[attr-defined]
    handler.setFormatter(PatternLogFormatter())
    return handler


def _configure_quiet_database_loggers() -> None:
    """Suppress SQLAlchemy/psycopg/asyncpg INFO/DEBUG query logs on the app sinks."""

    for logger_name in _QUIET_DATABASE_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)


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

    global _queue_listener, _atexit_registered

    level = normalize_log_level(level_name or settings.log_level)
    root = logging.getLogger()
    root.setLevel(level)
    _remove_managed_handlers(root)

    enable_stdout = settings.log_stdout_enabled if stdout_enabled is None else stdout_enabled
    enable_file = settings.log_file_enabled if file_enabled is None else file_enabled

    sink_handlers: list[logging.Handler] = []
    if enable_stdout:
        stream_handler = _mark_managed(logging.StreamHandler(sys.stdout))
        stream_handler.setLevel(level)
        sink_handlers.append(stream_handler)

    if enable_file:
        path = resolve_log_file_path(process_type, log_dir)
        path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = WindowsSafeTimedRotatingFileHandler(
            filename=path,
            when="midnight",
            backupCount=retention_days or settings.log_retention_days,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        sink_handlers.append(_mark_managed(file_handler))

    if sink_handlers:
        log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)
        queue_handler = QueueHandler(log_queue)
        queue_handler._minerva_logging = True  # type: ignore[attr-defined]
        root.addHandler(queue_handler)
        _queue_listener = QueueListener(
            log_queue,
            *sink_handlers,
            respect_handler_level=True,
        )
        _queue_listener.start()
        if not _atexit_registered:
            atexit.register(_stop_queue_listener)
            _atexit_registered = True

    for logger_name in ("uvicorn", "uvicorn.error", "celery"):
        logging.getLogger(logger_name).setLevel(level)
    logging.getLogger("uvicorn.access").propagate = True
    # Uvicorn --reload uses watchfiles; its INFO chatter is not useful in app logs.
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    _configure_quiet_database_loggers()
    set_logging_context(process_type=process_type)
