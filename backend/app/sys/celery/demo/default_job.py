"""Demo Celery task ``demo.default_job`` with structured lifecycle logging."""

from __future__ import annotations

import json
import time
from collections.abc import Mapping
from typing import Any

from celery import Task, shared_task
from celery.utils.log import get_task_logger

# Celery wires this logger under ``celery.task`` so ``celery worker --loglevel=INFO`` prints it.
logger = get_task_logger(__name__)

# Max characters per log field so worker logs stay bounded for large payloads.
_LOG_PREVIEW_LIMIT = 2000


def _payload_preview(value: Any, *, limit: int = _LOG_PREVIEW_LIMIT) -> str:
    """Render ``value`` as a single log-safe string (JSON when possible)."""

    try:
        raw = json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        raw = repr(value)
    if len(raw) > limit:
        return f"{raw[: limit - 3]}..."
    return raw


def _request_log_extra(request: Any) -> dict[str, Any]:
    """Build logging ``extra`` dict from Celery ``Request`` (worker-friendly fields)."""

    return {
        "celery_task_id": getattr(request, "id", None),
        "celery_task": getattr(request, "task", None),
        "celery_retries": getattr(request, "retries", 0),
        "celery_hostname": getattr(request, "hostname", None),
    }


@shared_task(bind=True, name="demo.default_job")
def default_job(self: Task, *args: Any, **kwargs: Any) -> dict[str, Any]:
    """Execute a no-op demo job and write start/finish lines to the worker logger.

    Logs use Celery's task logger (see worker terminal with ``--loglevel=INFO``, not the API process).
    The return value is JSON-serializable for the result backend.

    Args:
        self: Bound Celery task instance (``bind=True``).
        *args: Positional arguments passed from the scheduler or ``run-now``.
        **kwargs: Keyword arguments passed from the scheduler or ``run-now``.

    Returns:
        dict[str, Any]: Small summary including previews and timing for tracing.
    """

    request = self.request
    extra = _request_log_extra(request)
    started = time.perf_counter()

    logger.info(
        "demo.default_job start args=%s kwargs=%s",
        _payload_preview(list(args)),
        _payload_preview(kwargs),
        extra=extra,
    )

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    message = "default job completed successfully"

    logger.info(
        "demo.default_job finish task_id=%s elapsed_ms=%s",
        extra["celery_task_id"],
        elapsed_ms,
        extra=extra,
    )

    headers = getattr(request, "headers", None)
    if headers is None:
        headers_out = None
    elif isinstance(headers, Mapping):
        headers_out = dict(headers)
    else:
        headers_out = headers

    return {
        "ok": True,
        "message": message,
        "task_id": extra["celery_task_id"],
        "elapsed_ms": elapsed_ms,
        "args_preview": _payload_preview(list(args), limit=500),
        "kwargs_preview": _payload_preview(kwargs, limit=500),
        "request_headers": headers_out,
    }
