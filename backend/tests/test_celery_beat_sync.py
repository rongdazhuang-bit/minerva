"""Unit tests for beat bootstrap and Redis-driven incremental sync logic."""

from __future__ import annotations

from app.sys.celery.service.beat_bootstrap import (
    build_state_from_jobs,
    run_reconcile_once_if_due,
)
from app.sys.celery.service.beat_sync_service import BeatSyncState, apply_sync_event


def test_bootstrap_builds_workspace_task_schedule_key() -> None:
    """Bootstrap should create schedule keys in ``workspace_id:task_code`` format."""

    state = build_state_from_jobs(
        [
            {
                "workspace_id": "ws-001",
                "job_id": "job-001",
                "task_code": "report.daily",
                "task": "app.tasks.report_daily",
                "cron": "0 8 * * *",
                "args_json": ["daily"],
                "kwargs_json": {"force": True},
                "timezone": "Asia/Shanghai",
                "enabled": True,
                "version": 5,
            }
        ]
    )

    assert "ws-001:report.daily" in state.schedule
    entry = state.schedule["ws-001:report.daily"]
    assert entry["task"] == "app.tasks.report_daily"
    assert entry["version"] == 5


def test_apply_sync_event_ignores_older_version() -> None:
    """Idempotency guard should ignore stale events with old versions."""

    state = BeatSyncState(
        schedule={
            "ws-001:report.daily": {
                "task": "app.tasks.report_daily",
                "cron": "0 8 * * *",
                "args": [],
                "kwargs": {},
                "timezone": "Asia/Shanghai",
                "job_id": "job-001",
                "workspace_id": "ws-001",
                "task_code": "report.daily",
                "version": 3,
            }
        },
        job_versions={"ws-001:job-001": 3},
        job_schedule_keys={"ws-001:job-001": "ws-001:report.daily"},
    )

    applied = apply_sync_event(
        state,
        {"workspace_id": "ws-001", "job_id": "job-001", "op": "update", "version": 2},
        job_payload={
            "task_code": "report.daily",
            "task": "app.tasks.report_daily",
            "cron": "*/5 * * * *",
            "args_json": [],
            "kwargs_json": {},
            "timezone": "Asia/Shanghai",
            "enabled": True,
        },
    )

    assert applied is False
    assert state.schedule["ws-001:report.daily"]["cron"] == "0 8 * * *"


def test_update_event_overrides_cron_entry() -> None:
    """Update event should replace existing schedule entry cron expression."""

    state = BeatSyncState(
        schedule={
            "ws-001:report.daily": {
                "task": "app.tasks.report_daily",
                "cron": "0 8 * * *",
                "args": [],
                "kwargs": {},
                "timezone": "Asia/Shanghai",
                "job_id": "job-001",
                "workspace_id": "ws-001",
                "task_code": "report.daily",
                "version": 1,
            }
        },
        job_versions={"ws-001:job-001": 1},
        job_schedule_keys={"ws-001:job-001": "ws-001:report.daily"},
    )

    applied = apply_sync_event(
        state,
        {"workspace_id": "ws-001", "job_id": "job-001", "op": "update", "version": 2},
        job_payload={
            "task_code": "report.daily",
            "task": "app.tasks.report_daily",
            "cron": "*/5 * * * *",
            "args_json": ["daily"],
            "kwargs_json": {"force": False},
            "timezone": "Asia/Shanghai",
            "enabled": True,
        },
    )

    assert applied is True
    assert state.schedule["ws-001:report.daily"]["cron"] == "*/5 * * * *"
    assert state.schedule["ws-001:report.daily"]["version"] == 2


def test_delete_and_stop_events_remove_schedule() -> None:
    """Delete/stop events should evict schedule entries for the job."""

    state = BeatSyncState(
        schedule={
            "ws-001:report.daily": {
                "task": "app.tasks.report_daily",
                "cron": "0 8 * * *",
                "args": [],
                "kwargs": {},
                "timezone": "Asia/Shanghai",
                "job_id": "job-001",
                "workspace_id": "ws-001",
                "task_code": "report.daily",
                "version": 2,
            },
            "ws-001:report.hourly": {
                "task": "app.tasks.report_hourly",
                "cron": "0 * * * *",
                "args": [],
                "kwargs": {},
                "timezone": "Asia/Shanghai",
                "job_id": "job-002",
                "workspace_id": "ws-001",
                "task_code": "report.hourly",
                "version": 2,
            },
        },
        job_versions={"ws-001:job-001": 2, "ws-001:job-002": 2},
        job_schedule_keys={
            "ws-001:job-001": "ws-001:report.daily",
            "ws-001:job-002": "ws-001:report.hourly",
        },
    )

    deleted = apply_sync_event(
        state,
        {
            "workspace_id": "ws-001",
            "job_id": "job-001",
            "op": "delete",
            "version": 3,
            "task_code": "report.daily",
        },
    )
    stopped = apply_sync_event(
        state,
        {
            "workspace_id": "ws-001",
            "job_id": "job-002",
            "op": "stop",
            "version": 3,
            "task_code": "report.hourly",
        },
    )

    assert deleted is True
    assert stopped is True
    assert "ws-001:report.daily" not in state.schedule
    assert "ws-001:report.hourly" not in state.schedule


def test_run_reconcile_once_if_due_wires_interval_gate() -> None:
    """Reconcile entry should skip before interval and run when due."""

    state = BeatSyncState(
        schedule={
            "ws-001:report.daily": {
                "task": "app.tasks.report_daily",
                "cron": "0 8 * * *",
                "args": [],
                "kwargs": {},
                "timezone": "Asia/Shanghai",
                "job_id": "job-001",
                "workspace_id": "ws-001",
                "task_code": "report.daily",
                "version": 1,
            }
        },
        job_versions={"ws-001:job-001": 1},
        job_schedule_keys={"ws-001:job-001": "ws-001:report.daily"},
    )
    rows = [
        {
            "workspace_id": "ws-001",
            "job_id": "job-001",
            "task_code": "report.daily",
            "task": "app.tasks.report_daily",
            "cron": "*/10 * * * *",
            "args_json": [],
            "kwargs_json": {},
            "timezone": "Asia/Shanghai",
            "enabled": True,
            "version": 2,
        }
    ]

    same_last, skipped = run_reconcile_once_if_due(
        state,
        rows,
        now_epoch_seconds=120.0,
        last_reconcile_epoch_seconds=100.0,
        interval_seconds=60,
    )
    assert same_last == 100.0
    assert skipped["ran"] is False
    assert state.schedule["ws-001:report.daily"]["cron"] == "0 8 * * *"

    new_last, ran = run_reconcile_once_if_due(
        state,
        rows,
        now_epoch_seconds=170.0,
        last_reconcile_epoch_seconds=100.0,
        interval_seconds=60,
    )
    assert new_last == 170.0
    assert ran["ran"] is True
    assert state.schedule["ws-001:report.daily"]["cron"] == "*/10 * * * *"
    assert state.job_versions["ws-001:job-001"] == 2

