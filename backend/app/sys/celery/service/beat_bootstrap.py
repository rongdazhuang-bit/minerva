"""Startup bootstrap that loads enabled celery schedules for beat."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.sys.celery.domain.db.models import SysCelery
from app.sys.celery.service.beat_sync_service import (
    BeatSyncState,
    build_event_identity,
    build_schedule_entry,
    build_schedule_key,
)


def _row_to_payload(row: SysCelery | Mapping[str, Any]) -> dict[str, Any]:
    """Normalize ORM row or mapping to beat schedule payload."""

    if isinstance(row, Mapping):
        return {
            "workspace_id": str(row["workspace_id"]),
            "job_id": str(row["job_id"]),
            "task_code": str(row["task_code"]),
            "task": str(row["task"]),
            "cron": row.get("cron"),
            "args_json": row.get("args_json"),
            "kwargs_json": row.get("kwargs_json"),
            "timezone": row.get("timezone"),
            "enabled": bool(row.get("enabled", True)),
            "version": int(row.get("version") or 0),
        }
    return {
        "workspace_id": str(row.workspace_id),
        "job_id": str(row.id),
        "task_code": row.task_code,
        "task": row.task,
        "cron": row.cron,
        "args_json": row.args_json,
        "kwargs_json": row.kwargs_json,
        "timezone": row.timezone,
        "enabled": bool(row.enabled),
        "version": int(row.version or 0),
    }


def build_state_from_jobs(rows: Iterable[SysCelery | Mapping[str, Any]]) -> BeatSyncState:
    """Build initial beat sync state from all enabled job rows."""

    state = BeatSyncState()
    for row in rows:
        payload = _row_to_payload(row)
        if not payload["enabled"]:
            continue
        schedule_key = build_schedule_key(payload["workspace_id"], payload["task_code"])
        identity = build_event_identity(payload["workspace_id"], payload["job_id"])
        state.schedule[schedule_key] = build_schedule_entry(payload)
        state.job_versions[identity] = int(payload["version"])
        state.job_schedule_keys[identity] = schedule_key
    return state


async def load_enabled_schedule_state(session: AsyncSession) -> BeatSyncState:
    """Load all ``enabled=true`` rows from ``sys_celery`` for beat bootstrap."""

    result = await session.execute(select(SysCelery).where(SysCelery.enabled.is_(True)))
    rows = result.scalars().all()
    return build_state_from_jobs(rows)

