"""LangGraph ``AsyncPostgresSaver`` lifecycle (optional checkpoint tables)."""

from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from app.config import settings

log = logging.getLogger(__name__)

_checkpointer: BaseCheckpointSaver | None = None
_pool: AsyncConnectionPool | None = None
_setup_done = False


def _checkpoint_dsn() -> str:
    """Return a psycopg-compatible DSN from sync or async SQLAlchemy URLs."""

    raw = (settings.sync_database_url or settings.database_url or "").strip()
    for prefix in (
        "postgresql+psycopg2://",
        "postgresql+psycopg://",
        "postgresql+asyncpg://",
        "postgresql://",
    ):
        if raw.startswith(prefix):
            return "postgresql://" + raw.split("://", 1)[1]
    return raw


def _checkpoint_pool_sizes() -> tuple[int, int]:
    """Return validated ``(min_size, max_size)`` for the checkpoint pool."""

    min_size = settings.agent_langgraph_checkpoint_pool_min_size
    max_size = max(
        settings.agent_langgraph_checkpoint_pool_max_size,
        min_size,
    )
    return min_size, max_size


def _create_checkpoint_pool() -> AsyncConnectionPool:
    """Build a psycopg async pool for LangGraph checkpoint reads/writes."""

    min_size, max_size = _checkpoint_pool_sizes()
    timeout = settings.agent_langgraph_checkpoint_pool_timeout
    return AsyncConnectionPool(
        conninfo=_checkpoint_dsn(),
        open=False,
        min_size=min_size,
        max_size=max_size,
        timeout=timeout,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
        check=AsyncConnectionPool.check_connection,
    )


async def get_langgraph_checkpointer() -> BaseCheckpointSaver | None:
    """Return a shared checkpointer, or ``None`` if disabled or setup failed."""

    global _checkpointer, _pool, _setup_done
    if not settings.agent_langgraph_checkpoint_enabled:
        return None
    if _checkpointer is not None:
        return _checkpointer
    if _setup_done:
        return None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        min_size, max_size = _checkpoint_pool_sizes()
        timeout = settings.agent_langgraph_checkpoint_pool_timeout
        _pool = _create_checkpoint_pool()
        await _pool.open(wait=True, timeout=timeout)
        saver = AsyncPostgresSaver(conn=_pool)
        await saver.setup()
        _checkpointer = saver
        log.info(
            "LangGraph AsyncPostgresSaver ready "
            "(pool min=%s max=%s timeout=%ss, connection pre-check enabled)",
            min_size,
            max_size,
            timeout,
        )
    except Exception as e:
        log.warning("LangGraph checkpoint disabled: %s", e)
        _checkpointer = None
        if _pool is not None:
            try:
                await _pool.close()
            except Exception:
                pass
            _pool = None
    _setup_done = True
    return _checkpointer


async def reset_langgraph_checkpointer() -> BaseCheckpointSaver | None:
    """Close and recreate the checkpoint pool (recovery after pool timeouts)."""

    await close_langgraph_checkpointer()
    return await get_langgraph_checkpointer()


async def close_langgraph_checkpointer() -> None:
    """Close the shared checkpoint pool on application shutdown."""

    global _checkpointer, _pool, _setup_done
    _checkpointer = None
    _setup_done = False
    if _pool is None:
        return
    try:
        await _pool.close()
    except Exception as e:
        log.warning("LangGraph checkpoint pool close failed: %s", e)
    finally:
        _pool = None
