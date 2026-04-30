"""Celery application wiring and enqueue helper for runtime dispatch."""

from __future__ import annotations

from typing import Any

from app.config import settings
from app.exceptions import AppError


def _build_celery_app() -> Any:
    """Build one shared Celery application from process settings."""

    try:
        from celery import Celery
    except ModuleNotFoundError:
        return None

    celery_app = Celery(
        settings.app_name,
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )
    celery_app.conf.update(
        task_default_queue=settings.celery_default_queue,
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        enable_utc=True,
    )
    return celery_app


celery_app = _build_celery_app()


def enqueue_task(
    task_name: str,
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """Send one task to Celery broker and return accepted task id."""

    if celery_app is None:
        raise AppError("celery.runtime_unavailable", "Celery runtime is not installed", 503)
    result = celery_app.send_task(
        task_name,
        args=args or [],
        kwargs=kwargs or {},
        queue=settings.celery_default_queue,
    )
    return str(result.id)
