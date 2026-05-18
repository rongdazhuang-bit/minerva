"""LangGraph PostgresSaver with Minerva ``create_at`` / ``update_at`` columns."""

from __future__ import annotations

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# LangGraph UPSERT statements omit timestamp columns; defaults apply on INSERT.
# On conflict UPDATE we set ``update_at`` in SQL (no DB triggers).
UPSERT_CHECKPOINTS_SQL = """
    INSERT INTO checkpoints (thread_id, checkpoint_ns, checkpoint_id, parent_checkpoint_id, checkpoint, metadata)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id)
    DO UPDATE SET
        checkpoint = EXCLUDED.checkpoint,
        metadata = EXCLUDED.metadata,
        update_at = now();
"""

UPSERT_CHECKPOINT_WRITES_SQL = """
    INSERT INTO checkpoint_writes (thread_id, checkpoint_ns, checkpoint_id, task_id, task_path, idx, channel, type, blob)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (thread_id, checkpoint_ns, checkpoint_id, task_id, idx) DO UPDATE SET
        channel = EXCLUDED.channel,
        type = EXCLUDED.type,
        blob = EXCLUDED.blob,
        update_at = now();
"""


class MinervaAsyncPostgresSaver(AsyncPostgresSaver):
    """``AsyncPostgresSaver`` that maintains ``update_at`` on UPSERT in application SQL."""

    UPSERT_CHECKPOINTS_SQL = UPSERT_CHECKPOINTS_SQL
    UPSERT_CHECKPOINT_WRITES_SQL = UPSERT_CHECKPOINT_WRITES_SQL
