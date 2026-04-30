"""Redis-driven beat sync helpers for schedule hot reload and idempotency."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping, MutableMapping

from app.config import settings

# Redis pub/sub channel for celery beat schedule invalidation events.
SCHEDULE_CHANGED_EVENT = "schedule_changed"


def build_schedule_key(workspace_id: str, task_code: str) -> str:
    """Return canonical beat schedule key scoped by workspace and task code."""

    return f"{workspace_id}:{task_code}"


def build_event_identity(workspace_id: str, job_id: str) -> str:
    """Build stable idempotency identity for one workspace-level job."""

    return f"{workspace_id}:{job_id}"


def build_schedule_entry(job_payload: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one job payload to beat schedule entry data."""

    return {
        "task": str(job_payload["task"]),
        "cron": job_payload.get("cron"),
        "args": list(job_payload.get("args_json") or []),
        "kwargs": dict(job_payload.get("kwargs_json") or {}),
        "timezone": job_payload.get("timezone") or "Asia/Shanghai",
        "job_id": str(job_payload["job_id"]),
        "workspace_id": str(job_payload["workspace_id"]),
        "task_code": str(job_payload["task_code"]),
        "version": int(job_payload.get("version") or 0),
    }


@dataclass
class BeatSyncState:
    """In-memory state used by beat for incremental schedule application."""

    schedule: dict[str, dict[str, Any]] = field(default_factory=dict)
    job_versions: dict[str, int] = field(default_factory=dict)
    job_schedule_keys: dict[str, str] = field(default_factory=dict)


def publish_schedule_changed_event(
    payload: Mapping[str, Any],
    *,
    redis_client: Any | None = None,
) -> bool:
    """Publish one schedule-changed event to Redis pub/sub channel."""

    event = {
        "event": SCHEDULE_CHANGED_EVENT,
        "workspace_id": str(payload["workspace_id"]),
        "job_id": str(payload["job_id"]),
        "op": str(payload["op"]),
        "version": int(payload["version"]),
    }
    if payload.get("task_code"):
        event["task_code"] = str(payload["task_code"])
    if payload.get("enabled") is not None:
        event["enabled"] = bool(payload["enabled"])
    if payload.get("cron") is not None:
        event["cron"] = str(payload["cron"])

    close_client = False
    client = redis_client
    if client is None:
        try:
            import redis
        except ModuleNotFoundError:
            return False
        client = redis.Redis.from_url(settings.celery_broker_url, decode_responses=True)
        close_client = True

    message = json.dumps(event, separators=(",", ":"), ensure_ascii=True)
    try:
        client.publish(settings.celery_schedule_sync_channel, message)
    except Exception:
        return False
    finally:
        if close_client and client is not None:
            client.close()
    return True


def apply_sync_event(
    state: BeatSyncState,
    payload: Mapping[str, Any],
    *,
    job_payload: Mapping[str, Any] | None = None,
) -> bool:
    """Apply one incremental sync event with version-based idempotency guard."""

    workspace_id = str(payload["workspace_id"])
    job_id = str(payload["job_id"])
    version = int(payload["version"])
    op = str(payload["op"])
    identity = build_event_identity(workspace_id, job_id)
    previous_version = int(state.job_versions.get(identity, -1))
    if version <= previous_version:
        return False

    state.job_versions[identity] = version
    previous_schedule_key = state.job_schedule_keys.get(identity)
    if op in {"delete", "stop"}:
        schedule_key = previous_schedule_key or (
            build_schedule_key(workspace_id, str(payload["task_code"]))
            if payload.get("task_code")
            else None
        )
        if schedule_key:
            state.schedule.pop(schedule_key, None)
        state.job_schedule_keys.pop(identity, None)
        return True

    if job_payload is None:
        return False
    if job_payload.get("enabled") is False:
        if previous_schedule_key:
            state.schedule.pop(previous_schedule_key, None)
        state.job_schedule_keys.pop(identity, None)
        return True

    schedule_key = build_schedule_key(workspace_id, str(job_payload["task_code"]))
    if previous_schedule_key and previous_schedule_key != schedule_key:
        state.schedule.pop(previous_schedule_key, None)
    state.schedule[schedule_key] = build_schedule_entry(
        {
            **job_payload,
            "workspace_id": workspace_id,
            "job_id": job_id,
            "version": version,
        }
    )
    state.job_schedule_keys[identity] = schedule_key
    return True


def reconcile_schedule(
    state: BeatSyncState,
    expected_schedule: Mapping[str, Mapping[str, Any]],
) -> dict[str, int]:
    """Perform one low-frequency reconciliation pass and return change counters."""

    removed = 0
    updated = 0
    stale_keys = [key for key in state.schedule if key not in expected_schedule]
    for key in stale_keys:
        state.schedule.pop(key, None)
        removed += 1

    for key, value in expected_schedule.items():
        normalized = dict(value)
        if state.schedule.get(key) != normalized:
            state.schedule[key] = normalized
            updated += 1
    return {"removed": removed, "updated": updated}

