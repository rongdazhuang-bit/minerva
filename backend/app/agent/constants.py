"""Agent module shared constants."""

from __future__ import annotations

AGENT_CHECKPOINT_PURGE_TASK_NAME = "agent.checkpoint_purge"
AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY = AGENT_CHECKPOINT_PURGE_TASK_NAME

CHECKPOINT_PURGE_TABLES: tuple[str, ...] = (
    "checkpoint_writes",
    "checkpoint_blobs",
    "checkpoints",
)

_TABLE_RESULT_KEYS: dict[str, str] = {
    "checkpoint_writes": "writes",
    "checkpoint_blobs": "blobs",
    "checkpoints": "checkpoints",
}
