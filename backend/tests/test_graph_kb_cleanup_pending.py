"""Pending cleanup disk queue and flush behaviour."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

from app.graph_kb.infrastructure.pending_cleanup import (
    clear_pending_cleanup,
    iter_pending_cleanups,
    record_pending_cleanup,
)
from app.graph_kb.service.cleanup_service import flush_pending_cleanups


def _bind_pending_dir(tmp_path, monkeypatch) -> None:
    """Point pending cleanup storage at a pytest temp directory."""

    def fake_pending_dir():
        root = tmp_path / ".pending_cleanup"
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr(
        "app.graph_kb.infrastructure.pending_cleanup._pending_dir",
        fake_pending_dir,
    )


def test_record_and_clear_pending_cleanup(tmp_path, monkeypatch) -> None:
    """Pending files survive until cleanup succeeds or is re-enqueued."""

    _bind_pending_dir(tmp_path, monkeypatch)
    workspace_id = uuid4()
    graph_id = uuid4()
    record_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id, engine="lightrag")
    entries = iter_pending_cleanups()
    assert len(entries) == 1
    assert entries[0]["graph_id"] == str(graph_id)

    clear_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id)
    assert iter_pending_cleanups() == []


def test_flush_pending_cleanups_enqueues_and_removes(tmp_path, monkeypatch) -> None:
    """``flush_pending_cleanups`` re-sends Celery tasks for deferred deletes."""

    _bind_pending_dir(tmp_path, monkeypatch)
    workspace_id = uuid4()
    graph_id = uuid4()
    record_pending_cleanup(workspace_id=workspace_id, graph_id=graph_id, engine="graphrag")

    with patch(
        "app.graph_kb.service.cleanup_service._send_cleanup_task",
        return_value=True,
    ) as send_mock:
        flushed = flush_pending_cleanups()

    assert flushed == 1
    send_mock.assert_called_once_with(
        workspace_id=workspace_id,
        graph_id=graph_id,
        engine="graphrag",
    )
    assert iter_pending_cleanups() == []


def test_enqueue_cleanup_records_when_celery_unavailable(tmp_path, monkeypatch) -> None:
    """DELETE must succeed even when Celery is down; pending file enables retry."""

    import asyncio

    _bind_pending_dir(tmp_path, monkeypatch)
    workspace_id = uuid4()
    graph_id = uuid4()

    with patch(
        "app.graph_kb.service.cleanup_service._send_cleanup_task",
        return_value=False,
    ):
        from app.graph_kb.service.cleanup_service import enqueue_cleanup

        asyncio.run(
            enqueue_cleanup(
                workspace_id=workspace_id,
                graph_id=graph_id,
                engine="lightrag",
            )
        )

    entries = iter_pending_cleanups()
    assert len(entries) == 1
    assert entries[0]["engine"] == "lightrag"
