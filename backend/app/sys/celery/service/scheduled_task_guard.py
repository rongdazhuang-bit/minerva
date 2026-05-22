"""Prevent overlapping runs of the same ``sys_celery`` scheduled job via Redis lock."""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable, Mapping
from typing import Any, TypeVar

from celery import Task

from app.agent.constants import AGENT_CHECKPOINT_PURGE_TASK_NAME
from app.config import settings
from app.sys.celery.service.redis_connection import create_celery_redis_client

_LOGGER = logging.getLogger(__name__)

_LOCK_PREFIX = "minerva:celery:scheduled_singleton:"

# Celery request headers set by beat / run-now for per-job lock scope.
SCHEDULE_HEADER_WORKSPACE = "x-minerva-schedule-workspace-id"
SCHEDULE_HEADER_JOB = "x-minerva-schedule-job-id"
SCHEDULE_HEADER_TASK_CODE = "x-minerva-schedule-task-code"

# Task names that share one global lock (ignore workspace/job headers).
GLOBAL_SCHEDULED_SINGLETON_TASKS = frozenset({AGENT_CHECKPOINT_PURGE_TASK_NAME})

_SKIP_ALREADY_RUNNING: dict[str, Any] = {
    "skipped": True,
    "reason": "already_running",
}

_F = TypeVar("_F", bound=Callable[..., Any])


def build_schedule_run_headers(
    *,
    workspace_id: str,
    job_id: str,
    task_code: str,
) -> dict[str, str]:
    """Build Celery headers so run-now uses the same singleton scope as beat."""

    return {
        SCHEDULE_HEADER_WORKSPACE: workspace_id,
        SCHEDULE_HEADER_JOB: job_id,
        SCHEDULE_HEADER_TASK_CODE: task_code,
    }


def _request_headers(request: Any) -> dict[str, Any]:
    """Normalize Celery ``Request.headers`` to a plain dict."""

    raw = getattr(request, "headers", None)
    if raw is None:
        return {}
    if isinstance(raw, Mapping):
        return dict(raw)
    return {}


def resolve_scheduled_singleton_lock_key(
    task_name: str,
    headers: Mapping[str, Any] | None,
) -> str:
    """Return Redis lock key for one scheduled task invocation."""

    if task_name in GLOBAL_SCHEDULED_SINGLETON_TASKS:
        return f"{_LOCK_PREFIX}{task_name}"
    hdr = headers or {}
    workspace_id = str(hdr.get(SCHEDULE_HEADER_WORKSPACE, "") or "").strip()
    task_code = str(hdr.get(SCHEDULE_HEADER_TASK_CODE, "") or "").strip()
    if workspace_id and task_code:
        return f"{_LOCK_PREFIX}{task_name}:{workspace_id}:{task_code}"
    return f"{_LOCK_PREFIX}{task_name}"


def _redis_client() -> Any:
    """Create one Redis client with the same timeouts/health checks as Celery broker."""

    return create_celery_redis_client()


def try_acquire_scheduled_singleton_lock(lock_key: str, task_id: str) -> bool:
    """Try to acquire the singleton lock; return False when another run holds it."""

    ttl = int(settings.celery_scheduled_task_lock_ttl_seconds)
    try:
        client = _redis_client()
        acquired = client.set(lock_key, task_id, nx=True, ex=ttl)
        return bool(acquired)
    except Exception as exc:
        _LOGGER.warning(
            "scheduled singleton lock acquire failed key=%s: %s",
            lock_key,
            exc,
            exc_info=True,
        )
        return True


def release_scheduled_singleton_lock(lock_key: str, task_id: str) -> None:
    """Release the lock only when this invocation still owns it."""

    script = """
    if redis.call('get', KEYS[1]) == ARGV[1] then
        return redis.call('del', KEYS[1])
    end
    return 0
    """
    try:
        client = _redis_client()
        client.eval(script, 1, lock_key, task_id)
    except Exception as exc:
        _LOGGER.warning(
            "scheduled singleton lock release failed key=%s: %s",
            lock_key,
            exc,
            exc_info=True,
        )


def run_with_scheduled_singleton_guard(
    task: Task,
    run: Callable[[], Any],
) -> Any:
    """Execute ``run`` when no other worker holds the same scheduled lock; else skip."""

    task_name = str(task.name)
    task_id = str(getattr(task.request, "id", "") or "")
    lock_key = resolve_scheduled_singleton_lock_key(
        task_name,
        _request_headers(task.request),
    )
    if not try_acquire_scheduled_singleton_lock(lock_key, task_id):
        _LOGGER.info(
            "scheduled task skipped (already running) task=%s lock_key=%s task_id=%s",
            task_name,
            lock_key,
            task_id,
        )
        return {
            **_SKIP_ALREADY_RUNNING,
            "task": task_name,
            "lock_key": lock_key,
        }
    try:
        return run()
    finally:
        release_scheduled_singleton_lock(lock_key, task_id)


def scheduled_singleton_guard(func: _F) -> _F:
    """Decorator for ``@shared_task(bind=True)`` entries invoked from ``sys_celery``."""

    @functools.wraps(func)
    def wrapper(self: Task, *args: Any, **kwargs: Any) -> Any:
        return run_with_scheduled_singleton_guard(
            self,
            lambda: func(self, *args, **kwargs),
        )

    return wrapper  # type: ignore[return-value]
