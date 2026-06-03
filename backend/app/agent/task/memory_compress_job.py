"""Celery entry for mem0 long-term memory compression."""

from __future__ import annotations

from app.core.log import get_logger
from typing import Any

from celery import Task, shared_task

from app.agent.constants import AGENT_MEMORY_COMPRESS_TASK_NAME
from app.agent.service.memory_compress_service import run_mem0_memory_compress
from app.config import settings
from app.sys.celery.service.scheduled_task_guard import scheduled_singleton_guard

log = get_logger(__name__)


@shared_task(bind=True, name=AGENT_MEMORY_COMPRESS_TASK_NAME)
@scheduled_singleton_guard
def compress_mem0_memories(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Merge aged mem0 memories into summaries (mem0 backend only)."""

    log.info(
        "agent.memory.compress_mem0 start task_id={}",
        getattr(self.request, "id", None),
    )
    if settings.agent_memory_backend != "mem0":
        return {"skipped": True, "reason": "backend_not_mem0"}
    if not settings.agent_memory_compress_celery_enabled:
        return {"skipped": True, "reason": "celery_disabled"}
    summary = run_mem0_memory_compress()
    log.info("agent.memory.compress_mem0 done summary={}", summary)
    return summary
