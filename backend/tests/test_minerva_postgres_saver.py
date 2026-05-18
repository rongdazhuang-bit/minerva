"""Minerva LangGraph PostgresSaver UPSERT SQL for ``update_at``."""

from app.agent.infrastructure.minerva_postgres_saver import MinervaAsyncPostgresSaver


def test_checkpoints_upsert_sets_update_at_on_conflict() -> None:
    """Checkpoint UPSERT refreshes ``update_at`` in SQL without a DB trigger."""

    sql = MinervaAsyncPostgresSaver.UPSERT_CHECKPOINTS_SQL
    assert "update_at = now()" in sql


def test_checkpoint_writes_upsert_sets_update_at_on_conflict() -> None:
    """Write UPSERT refreshes ``update_at`` in SQL without a DB trigger."""

    sql = MinervaAsyncPostgresSaver.UPSERT_CHECKPOINT_WRITES_SQL
    assert "update_at = now()" in sql
