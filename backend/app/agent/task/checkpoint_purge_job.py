"""Celery entry for LangGraph checkpoint retention purge."""

from __future__ import annotations

from app.core.log import get_logger
from typing import Any

from celery import Task, shared_task
from sqlalchemy import create_engine

from app.agent.constants import AGENT_CHECKPOINT_PURGE_TASK_NAME
from app.agent.service.checkpoint_purge_service import run_checkpoint_purge
from app.config import settings
from app.sys.celery.service.scheduled_task_guard import scheduled_singleton_guard

log = get_logger(__name__)


def _sync_engine():
    """Build a one-off sync engine for purge SQL (not the LangGraph pool)."""

    return create_engine(
        settings.sync_database_url,
        pool_pre_ping=True,
        pool_size=1,
        max_overflow=0,
        future=True,
    )


@shared_task(bind=True, name=AGENT_CHECKPOINT_PURGE_TASK_NAME)
@scheduled_singleton_guard
def purge_langgraph_checkpoints(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Purge checkpoint tables older than configured retention (ignores beat args)."""

    log.info("agent.checkpoint_purge start task_id={}", getattr(self.request, "id", None))
    engine = _sync_engine()
    with engine.begin() as conn:
        summary = run_checkpoint_purge(conn)
    log.info("agent.checkpoint_purge done summary={}", summary)
    return summary
