"""Checkpoint retention purge settings and pure helpers."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.agent.constants import AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY
from app.agent.service import checkpoint_purge_service as svc
from app.config import settings


def test_advisory_lock_key_is_bigint() -> None:
    """Advisory lock key must be int64 for pg_try_advisory_lock(bigint)."""

    assert isinstance(AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY, int)
    assert -2**63 <= AGENT_CHECKPOINT_PURGE_ADVISORY_LOCK_KEY < 2**63


def test_retention_defaults() -> None:
    """Default retention is seven days with cleanup enabled."""

    assert settings.agent_langgraph_checkpoint_retention_days == 7
    assert settings.agent_langgraph_checkpoint_cleanup_enabled is True
    assert settings.agent_langgraph_checkpoint_cleanup_batch_size == 1000


def test_compute_cutoff_uses_utc() -> None:
    """Cutoff is now minus retention days in UTC."""

    now = datetime(2026, 5, 18, 12, 0, 0, tzinfo=timezone.utc)
    cutoff = svc.compute_cutoff(now=now, retention_days=7)
    assert cutoff == datetime(2026, 5, 11, 12, 0, 0, tzinfo=timezone.utc)


def test_purge_skipped_when_disabled(monkeypatch) -> None:
    """When cleanup is disabled, no SQL runs."""

    monkeypatch.setattr(svc, "_purge_enabled", lambda: False)
    conn = MagicMock()
    result = svc.run_checkpoint_purge(conn)
    assert result == {"skipped": True, "reason": "disabled"}
    conn.execute.assert_not_called()


def test_purge_skipped_when_lock_not_acquired(monkeypatch) -> None:
    """When advisory lock is busy, return without deleting."""

    monkeypatch.setattr(svc, "_purge_enabled", lambda: True)
    monkeypatch.setattr(svc, "_try_advisory_lock", lambda _conn: False)
    conn = MagicMock()
    result = svc.run_checkpoint_purge(conn)
    assert result == {"skipped": True, "reason": "lock"}
    conn.execute.assert_not_called()


def test_delete_batch_once() -> None:
    """One batch delete returns cursor rowcount."""

    conn = MagicMock()
    conn.execute.return_value.rowcount = 3
    cutoff = svc.compute_cutoff(
        now=datetime(2026, 5, 18, tzinfo=timezone.utc),
        retention_days=7,
    )
    deleted = svc._delete_expired_batch(
        conn,
        table="checkpoint_writes",
        cutoff=cutoff,
        batch_size=1000,
    )
    assert deleted == 3
    sql = str(conn.execute.call_args[0][0])
    assert "checkpoint_writes" in sql
    assert "create_at" in sql


def test_purge_all_tables_loops_until_zero(monkeypatch) -> None:
    """Each table is drained in batches until a batch deletes zero rows."""

    monkeypatch.setattr(svc, "_purge_enabled", lambda: True)
    monkeypatch.setattr(svc, "_try_advisory_lock", lambda _conn: True)
    monkeypatch.setattr(svc, "_release_advisory_lock", lambda _conn: None)
    counts = iter([2, 0, 1, 0, 0])
    monkeypatch.setattr(svc, "_delete_expired_batch", lambda *a, **k: next(counts))
    conn = MagicMock()
    result = svc.run_checkpoint_purge(conn)
    assert result["writes"] == 2
    assert result["blobs"] == 1
    assert result["checkpoints"] == 0
    assert result["skipped"] is False
