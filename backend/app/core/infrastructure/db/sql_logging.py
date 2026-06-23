"""Optional SQL statement logging with execution timing for SQLAlchemy engines."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config import settings
from app.core.log import get_logger
from app.core.logging_text import format_log_value

log = get_logger("app.db.sql")

_SQL_LOGGING_ATTR = "_minerva_sql_logging_attached"
_QUERY_START_STACK_KEY = "_minerva_sql_query_start_stack"


def attach_sql_logging_if_enabled(engine: Engine | AsyncEngine) -> None:
    """Register before/after cursor listeners on one sync or async engine when enabled."""

    if not settings.log_sql_enabled:
        return
    target = engine.sync_engine if isinstance(engine, AsyncEngine) else engine
    if getattr(target, _SQL_LOGGING_ATTR, False):
        return
    setattr(target, _SQL_LOGGING_ATTR, True)
    _register_sql_timing_listeners(target)


def create_app_sync_engine(url: str, **kwargs: Any) -> Engine:
    """Create a sync SQLAlchemy engine and attach SQL timing listeners when configured."""

    engine = create_engine(url, **kwargs)
    attach_sql_logging_if_enabled(engine)
    return engine


def create_app_async_engine(url: str, **kwargs: Any) -> AsyncEngine:
    """Create an async SQLAlchemy engine and attach SQL timing listeners when configured."""

    engine = create_async_engine(url, **kwargs)
    attach_sql_logging_if_enabled(engine)
    return engine


def _register_sql_timing_listeners(engine: Engine) -> None:
    """Install cursor execute hooks that log SQL text and elapsed milliseconds."""

    @event.listens_for(engine, "before_cursor_execute")
    def _before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        stack: list[float] = conn.info.setdefault(_QUERY_START_STACK_KEY, [])
        stack.append(time.perf_counter())

    @event.listens_for(engine, "after_cursor_execute")
    def _after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        stack: list[float] = conn.info.get(_QUERY_START_STACK_KEY, [])
        if not stack:
            return
        started = stack.pop()
        duration_ms = (time.perf_counter() - started) * 1000.0
        prefix = "SQL executemany" if executemany else "SQL"
        log.info(
            "{} duration_ms={} statement={} parameters={}",
            prefix,
            f"{duration_ms:.3f}",
            statement,
            format_log_value(parameters),
        )
