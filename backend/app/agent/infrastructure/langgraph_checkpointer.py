"""LangGraph ``AsyncPostgresSaver`` lifecycle (optional checkpoint tables)."""

from __future__ import annotations

import logging

from langgraph.checkpoint.base import BaseCheckpointSaver

from app.config import settings

log = logging.getLogger(__name__)

_checkpointer: BaseCheckpointSaver | None = None
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


async def get_langgraph_checkpointer() -> BaseCheckpointSaver | None:
    """Return a shared checkpointer, or ``None`` if disabled or setup failed."""

    global _checkpointer, _setup_done
    if not settings.agent_langgraph_checkpoint_enabled:
        return None
    if _checkpointer is not None:
        return _checkpointer
    if _setup_done:
        return None
    try:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

        saver = AsyncPostgresSaver.from_conn_string(_checkpoint_dsn())
        await saver.setup()
        _checkpointer = saver
        log.info("LangGraph AsyncPostgresSaver ready")
    except Exception as e:
        log.warning("LangGraph checkpoint disabled: %s", e)
        _checkpointer = None
    _setup_done = True
    return _checkpointer
