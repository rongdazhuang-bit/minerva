"""Celery Scheduler that loads periodic entries from PostgreSQL ``sys_celery``."""

from __future__ import annotations

import logging
import threading
from typing import Any

from celery.beat import Scheduler
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.sys.celery.domain.db.models import SysCelery
from app.sys.celery.service.task_payload_codec import normalize_task_args, normalize_task_kwargs

from .cron_schedule import cron_expr_to_celery_schedule

_LOGGER = logging.getLogger(__name__)

_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _ensure_sync_engine() -> None:
    """Lazily build one sync SQLAlchemy engine bound to ``sync_database_url``."""

    global _engine, _SessionLocal  # noqa: PLW0603

    if _engine is None:
        _engine = create_engine(
            settings.sync_database_url,
            pool_pre_ping=True,
            pool_size=2,
            max_overflow=0,
            future=True,
        )
        _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


def _schedule_entry_key(row: SysCelery) -> str:
    """Return stable beat entry name scoped by workspace and task_code."""

    return f"minerva:{row.workspace_id}:{row.task_code}"


class MinervaBeatScheduler(Scheduler):
    """Loads enabled jobs via ``sync_database_url`` plus optional Redis-triggered reloads."""

    #: How long (seconds) idle beat waits before reloading rows from Postgres.
    reconcile_seconds: int = 60

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        """Prepare reconcile interval, Redis hot-reload primitives, then build the heap."""

        self.reconcile_seconds = max(15, min(3600, int(settings.celery_schedule_reconcile_seconds)))
        self._hot_reload_event = threading.Event()
        self._listener_stop = threading.Event()
        self._listener_thread: threading.Thread | None = None
        super().__init__(*args, **kwargs)
        self.sync_every = float(self.reconcile_seconds)

    def setup_schedule(self) -> None:
        """Apply static ``beat_schedule``, merge Postgres jobs, start Redis subscriber."""

        super().setup_schedule()
        rows = self._enabled_rows()
        payload = self._rows_to_schedule_dict(rows)
        self.merge_inplace(payload)
        if rows:
            _LOGGER.info(
                "minerva beat: loaded %s enabled celery job(s) from Postgres",
                len(rows),
            )
        else:
            _LOGGER.warning(
                "minerva beat: no enabled sys_celery rows with valid cron "
                "(check DB and ENABLED/CRON fields)",
            )
        self._ensure_hot_reload_listener()

    def close(self) -> None:
        """Stop pub/sub thread then persist/sync through the base scheduler."""

        self._stop_hot_reload_listener()
        super().close()

    def tick(self, *args: Any, **kwargs: Any) -> float:
        """Apply any pending Redis hot-reload before the standard beat tick progression."""

        if self._hot_reload_event.is_set():
            self._hot_reload_event.clear()
            _LOGGER.info("minerva beat: reloading schedules after Redis notify")
            self.sync()
            self.old_schedulers = None
            self._heap = None

        result = super().tick(*args, **kwargs)
        return float(result)

    def _ensure_hot_reload_listener(self) -> None:
        """Start a daemon thread subscribing to workspace schedule-change publishes."""

        if not settings.celery_beat_hot_reload_via_redis:
            return
        if self._listener_thread is not None and self._listener_thread.is_alive():
            return
        self._listener_stop.clear()
        thread = threading.Thread(
            target=self._redis_listen_loop,
            name="minerva-celery-beat-sync",
            daemon=True,
        )
        self._listener_thread = thread
        thread.start()
        _LOGGER.info(
            "minerva beat: Redis hot-reload listener on channel %s",
            settings.celery_schedule_sync_channel,
        )

    def _stop_hot_reload_listener(self) -> None:
        """Signal the subscriber thread to exit and join briefly on shutdown."""

        self._listener_stop.set()
        if self._listener_thread is not None and self._listener_thread.is_alive():
            self._listener_thread.join(timeout=3.0)

    def _redis_listen_loop(self) -> None:
        """Consume schedule_changed JSON messages and flag the beat thread to resync Postgres."""

        try:
            import redis as redis_mod
        except ModuleNotFoundError:
            _LOGGER.warning("minerva beat: redis package missing; skipping hot-reload listener")
            return

        client = None
        pubsub = None
        try:
            client = redis_mod.Redis.from_url(settings.celery_broker_url, decode_responses=True)
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(settings.celery_schedule_sync_channel)
            while not self._listener_stop.is_set():
                message = pubsub.get_message(timeout=1.0)
                if message is None or message.get("type") != "message":
                    continue
                self._hot_reload_event.set()
        except Exception as exc:
            _LOGGER.warning(
                "minerva beat: Redis listener exited with error: %s",
                exc,
                exc_info=True,
            )
        finally:
            if pubsub is not None:
                try:
                    pubsub.close()
                except Exception:
                    pass
            if client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    def sync(self) -> None:
        """Reload Postgres definitions so CRUD reaches beat without restarting."""

        _ensure_sync_engine()
        try:
            rows = self._enabled_rows()
            self.merge_inplace(self._rows_to_schedule_dict(rows))
        except Exception as exc:
            _LOGGER.warning("minerva beat: reload from Postgres failed: %s", exc, exc_info=True)

    def _enabled_rows(self) -> list[SysCelery]:
        """Fetch all enabled celery schedule rows."""

        _ensure_sync_engine()
        assert _SessionLocal is not None
        with _SessionLocal() as session:
            stmt = (
                select(SysCelery)
                .where(SysCelery.enabled.is_(True))
                .where(SysCelery.cron.isnot(None))
                .order_by(SysCelery.create_at.asc().nulls_last(), SysCelery.id.asc())
            )
            return list(session.scalars(stmt))

    def _rows_to_schedule_dict(self, rows: list[SysCelery]) -> dict[str, dict[str, Any]]:
        """Build Celery merge_inplace payload from ORM rows (skips malformed cron)."""

        out: dict[str, dict[str, Any]] = {}
        for row in rows:
            name = _schedule_entry_key(row)
            try:
                if not row.cron or not str(row.cron).strip():
                    continue
                sched = cron_expr_to_celery_schedule(
                    str(row.cron),
                    app=self.app,
                    timezone_name=row.timezone or "Asia/Shanghai",
                )
                kwargs_payload = normalize_task_kwargs(row.kwargs_json)
            except ValueError as exc:
                _LOGGER.warning(
                    "minerva beat: skip job %s / %s: %s",
                    row.id,
                    row.task_code,
                    exc,
                )
                continue
            except TypeError as exc:
                _LOGGER.warning(
                    "minerva beat: skip job %s / %s (invalid kwargs_json): %s",
                    row.id,
                    row.task_code,
                    exc,
                )
                continue
            out[name] = {
                "task": row.task.strip(),
                "schedule": sched,
                "args": tuple(normalize_task_args(row.args_json)),
                "kwargs": kwargs_payload,
                "options": {"queue": settings.celery_default_queue},
            }
        return out
