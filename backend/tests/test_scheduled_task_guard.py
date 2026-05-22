"""Unit tests for scheduled Celery task singleton guard."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.agent.constants import AGENT_CHECKPOINT_PURGE_TASK_NAME
from app.sys.celery.service import scheduled_task_guard as guard


def test_resolve_lock_key_global_singleton() -> None:
    """Global scheduled tasks use one lock per task name."""

    key = guard.resolve_scheduled_singleton_lock_key(
        AGENT_CHECKPOINT_PURGE_TASK_NAME,
        {
            guard.SCHEDULE_HEADER_WORKSPACE: "ws-1",
            guard.SCHEDULE_HEADER_TASK_CODE: "agent_checkpoint_purge",
        },
    )
    assert key == f"minerva:celery:scheduled_singleton:{AGENT_CHECKPOINT_PURGE_TASK_NAME}"


def test_resolve_lock_key_scoped_by_workspace_and_task_code() -> None:
    """Per-job scheduled tasks lock on workspace + task_code from beat headers."""

    key = guard.resolve_scheduled_singleton_lock_key(
        "demo.default_job",
        {
            guard.SCHEDULE_HEADER_WORKSPACE: "ws-1",
            guard.SCHEDULE_HEADER_TASK_CODE: "demo_daily",
        },
    )
    assert key == "minerva:celery:scheduled_singleton:demo.default_job:ws-1:demo_daily"


def test_resolve_lock_key_falls_back_to_task_name() -> None:
    """Manual enqueue without schedule headers still serializes by task name."""

    key = guard.resolve_scheduled_singleton_lock_key("demo.default_job", {})
    assert key == "minerva:celery:scheduled_singleton:demo.default_job"


def test_run_with_guard_skips_when_lock_not_acquired() -> None:
    """Second invocation returns already_running without calling the body."""

    task = SimpleNamespace(
        name="demo.default_job",
        request=SimpleNamespace(id="task-b", headers={}),
    )
    body = MagicMock(return_value={"ok": True})

    with patch.object(guard, "try_acquire_scheduled_singleton_lock", return_value=False):
        out = guard.run_with_scheduled_singleton_guard(task, body)

    assert out["skipped"] is True
    assert out["reason"] == "already_running"
    body.assert_not_called()


def test_run_with_guard_releases_lock_after_success() -> None:
    """Lock is released in ``finally`` after the wrapped function completes."""

    task = SimpleNamespace(
        name="demo.default_job",
        request=SimpleNamespace(id="task-a", headers={}),
    )
    body = MagicMock(return_value={"ok": True})

    with (
        patch.object(guard, "try_acquire_scheduled_singleton_lock", return_value=True) as acquire,
        patch.object(guard, "release_scheduled_singleton_lock") as release,
    ):
        out = guard.run_with_scheduled_singleton_guard(task, body)

    assert out == {"ok": True}
    acquire.assert_called_once()
    release.assert_called_once()
    body.assert_called_once()
