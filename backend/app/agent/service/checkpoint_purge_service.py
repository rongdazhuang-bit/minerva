"""LangGraph checkpoint table retention purge (sync SQL)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.engine import Connection

from app.agent.constants import (
    AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY,
    CHECKPOINT_PURGE_TABLES,
    _TABLE_RESULT_KEYS,
)
from app.config import settings

_DELETE_SQL = """
DELETE FROM {table}
WHERE ctid IN (
  SELECT ctid FROM {table}
  WHERE create_at < :cutoff
  LIMIT :batch
)
"""


def compute_cutoff(*, now: datetime, retention_days: int) -> datetime:
    """Return UTC cutoff; rows with ``create_at`` strictly before this are expired."""

    if now.tzinfo is None:
        aware = now.replace(tzinfo=timezone.utc)
    else:
        aware = now.astimezone(timezone.utc)
    return aware - timedelta(days=retention_days)


def _purge_enabled() -> bool:
    """Return whether scheduled checkpoint purge is enabled in settings."""

    return settings.agent_langgraph_checkpoint_cleanup_enabled


def _try_advisory_lock(conn: Connection) -> bool:
    """Try to acquire the global purge advisory lock for this connection."""

    acquired = conn.execute(
        text("SELECT pg_try_advisory_lock(:key)"),
        {"key": AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY},
    ).scalar()
    return bool(acquired)


def _release_advisory_lock(conn: Connection) -> None:
    """Release the global purge advisory lock for this connection."""

    conn.execute(
        text("SELECT pg_advisory_unlock(:key)"),
        {"key": AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY},
    )


def _delete_expired_batch(
    conn: Connection,
    *,
    table: str,
    cutoff: datetime,
    batch_size: int,
) -> int:
    """Delete up to ``batch_size`` expired rows from one checkpoint table."""

    if table not in CHECKPOINT_PURGE_TABLES:
        raise ValueError(f"unsupported checkpoint table: {table}")
    result = conn.execute(
        text(_DELETE_SQL.format(table=table)),
        {"cutoff": cutoff, "batch": batch_size},
    )
    return int(result.rowcount or 0)


def _purge_table(
    conn: Connection,
    *,
    table: str,
    cutoff: datetime,
    batch_size: int,
) -> int:
    """Delete all expired rows from ``table`` in batches."""

    total = 0
    while True:
        deleted = _delete_expired_batch(
            conn,
            table=table,
            cutoff=cutoff,
            batch_size=batch_size,
        )
        total += deleted
        if deleted == 0:
            return total


def run_checkpoint_purge(conn: Connection) -> dict[str, object]:
    """Delete expired checkpoint rows; safe to call from Celery."""

    if not _purge_enabled():
        return {"skipped": True, "reason": "disabled"}
    if not _try_advisory_lock(conn):
        return {"skipped": True, "reason": "lock"}
    try:
        cutoff = compute_cutoff(
            now=datetime.now(timezone.utc),
            retention_days=settings.agent_langgraph_checkpoint_retention_days,
        )
        batch_size = settings.agent_langgraph_checkpoint_cleanup_batch_size
        summary: dict[str, object] = {
            "skipped": False,
            "cutoff": cutoff.isoformat(),
        }
        for table in CHECKPOINT_PURGE_TABLES:
            summary[_TABLE_RESULT_KEYS[table]] = _purge_table(
                conn,
                table=table,
                cutoff=cutoff,
                batch_size=batch_size,
            )
        return summary
    finally:
        _release_advisory_lock(conn)
