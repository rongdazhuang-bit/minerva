"""Celery application wiring and enqueue helper for runtime dispatch.

Beat process can reuse this module as a stable integration surface:
- ``bootstrap_beat_runtime(session)`` on startup
- ``apply_beat_sync_message(...)`` when receiving one schedule sync payload
- ``run_beat_reconcile_cycle(...)`` in periodic reconcile ticks

On Windows the default prefork/billiard pool can leave ``trace._localized`` empty in worker
children, causing ``ValueError: not enough values to unpack (expected 3, got 0)`` in
``fast_trace_task``. This module defaults ``worker_pool`` to ``solo`` on Windows unless
``MINERVA_CELERY_USE_PREFORK`` is set to opt into prefork.
"""

from __future__ import annotations

import os
import sys
from socket import timeout as SocketTimeout
from typing import Any

from app.config import settings
from app.exceptions import AppError
from app.sys.celery.service.beat_runtime import (
    CeleryBeatRuntimeState,
    create_beat_runtime_state,
    process_sync_message_once,
    run_reconcile_cycle_once,
)

try:
    from kombu.exceptions import EncodeError as _KombuEncodeError
except ImportError:  # pragma: no cover - kombu ships with celery
    _KombuEncodeError = None  # type: ignore[misc, assignment]

try:
    from redis.exceptions import RedisError as _RedisError
except ImportError:  # pragma: no cover - optional in minimal installs
    _RedisError = None  # type: ignore[misc, assignment]

try:
    from kombu.exceptions import ConnectionError as _KombuBrokerConnectionError
except ImportError:  # pragma: no cover - kombu ships with celery
    _KombuBrokerConnectionError = None  # type: ignore[misc, assignment]


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
        # Let application/task loggers propagate; hijacking root often hides ``logging.getLogger(__name__)``.
        worker_hijack_root_logger=False,
    )

    _win_prefork = os.getenv("MINERVA_CELERY_USE_PREFORK", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    if sys.platform == "win32" and not _win_prefork:
        # Celery CLI defaults ``--pool`` to prefork; ``WorkersPool`` replaces that with
        # ``conf.worker_pool`` when the CLI value is still the prefork default (see celery.bin.worker).
        celery_app.conf.worker_pool = "solo"

    celery_app.conf.beat_scheduler = (
        "app.sys.celery.beat.minerva_scheduler:MinervaBeatScheduler"
    )
    celery_app.conf.beat_max_loop_interval = max(
        1,
        min(120, int(settings.celery_beat_max_loop_seconds)),
    )

    return celery_app


celery_app = _build_celery_app()

if celery_app is not None:
    # Registers ``shared_task`` symbols (e.g. ``demo.default_job``) on this app for workers.
    import app.sys.celery.demo.default_job  # noqa: F401

    try:
        from celery.app import trace as _celery_trace
        from celery.signals import worker_process_init

        def _ensure_fast_trace_locals(sender=None, **kwargs) -> None:
            """Populate ``celery.app.trace._localized`` in pool child processes when missing.

            On Windows (billiard spawn), ``process_initializer`` does not call
            ``setup_worker_optimizations``, so ``trace._localized`` stays empty in the
            child. The parent worker still dispatches ``fast_trace_task`` into the pool,
            which then unpacks ``_localized`` and raises
            ``ValueError: not enough values to unpack (expected 3, got 0)``.

            Primary mitigation is ``conf.worker_pool = "solo"`` on Windows above; this
            hook remains for operators who force prefork via ``MINERVA_CELERY_USE_PREFORK``.

            Do not gate on ``app.use_fast_trace_task``: that flag stays false in the
            child until ``setup_worker_optimizations`` runs, so an early return would
            skip the fix precisely when it is needed.
            """

            if len(_celery_trace._localized) >= 3:
                return
            _celery_trace.setup_worker_optimizations(celery_app)

        worker_process_init.connect(_ensure_fast_trace_locals, weak=False)
    except ImportError:
        pass


def _translate_enqueue_error(exc: Exception) -> AppError:
    """Map Celery/Kombu enqueue failures to stable domain errors.

    Treats JSON encoding issues as client/payload errors (422) and broker or
    transport outages as unavailable (503). Redis broker failures often surface
    as ``redis.exceptions.RedisError`` (e.g. auth failures), not only
    ``ConnectionError``. Kombu's AMQP ``ConnectionError`` does not subclass the
    builtin ``ConnectionError``, so it must be recognized explicitly.
    """

    if _KombuEncodeError is not None and isinstance(exc, _KombuEncodeError):
        detail = str(exc).strip() or "Task arguments are not JSON-serializable for Celery"
        return AppError(
            "celery.payload_not_serializable",
            detail,
            422,
        )
    if _RedisError is not None and isinstance(exc, _RedisError):
        return AppError(
            "celery.enqueue_unavailable",
            "Celery broker is unavailable",
            503,
        )
    if _KombuBrokerConnectionError is not None and isinstance(
        exc,
        _KombuBrokerConnectionError,
    ):
        return AppError(
            "celery.enqueue_unavailable",
            "Celery broker is unavailable",
            503,
        )
    error_name = exc.__class__.__name__
    if error_name in {"OperationalError", "ChannelError", "TimeoutError"} or isinstance(
        exc, (ConnectionError, TimeoutError, SocketTimeout)
    ):
        return AppError(
            "celery.enqueue_unavailable",
            "Celery broker is unavailable",
            503,
        )
    return AppError(
        "celery.enqueue_failed",
        "Celery enqueue failed",
        502,
    )


def enqueue_task(
    task_name: str,
    *,
    args: list[Any] | None = None,
    kwargs: dict[str, Any] | None = None,
) -> str:
    """Send one task to Celery broker and return accepted task id."""

    if celery_app is None:
        raise AppError("celery.runtime_unavailable", "Celery runtime is not installed", 503)
    try:
        result = celery_app.send_task(
            task_name,
            args=args or [],
            kwargs=kwargs or {},
            queue=settings.celery_default_queue,
        )
    except AppError:
        raise
    except Exception as exc:
        raise _translate_enqueue_error(exc) from exc
    return str(result.id)


async def bootstrap_beat_runtime(session: Any) -> CeleryBeatRuntimeState:
    """Bootstrap beat runtime state from enabled jobs at process startup."""

    return await create_beat_runtime_state(session)


def apply_beat_sync_message(
    runtime: CeleryBeatRuntimeState,
    payload: dict[str, Any],
    *,
    job_payload: dict[str, Any] | None = None,
) -> bool:
    """Apply one sync payload message inside a beat event loop tick."""

    return process_sync_message_once(runtime, payload, job_payload=job_payload)


def run_beat_reconcile_cycle(
    runtime: CeleryBeatRuntimeState,
    rows: list[dict[str, Any]],
    *,
    now_epoch_seconds: float,
    interval_seconds: int | None = None,
) -> dict[str, Any]:
    """Run one reconcile cycle; call from beat's periodic maintenance hook."""

    return run_reconcile_cycle_once(
        runtime,
        rows,
        now_epoch_seconds=now_epoch_seconds,
        interval_seconds=interval_seconds,
    )
