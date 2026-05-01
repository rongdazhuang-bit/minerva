"""Cron string normalization for Celery :class:`~celery.schedules.schedule` / ``crontab``."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any

# Matches simple "every N seconds" second field such as ``*/5``.
_SECOND_STEP = re.compile(r"^\*/(\d{1,2})$")


def _all_star(parts: tuple[str, ...]) -> bool:
    """Returns true when each field is a single wildcard "*"."""

    return all(p == "*" for p in parts)


def _attach_app_nowfun(sch: Any, *, app: Any, nowfun: Any) -> Any:
    """Bind Celery ``app`` plus job-local ``nowfun`` onto a schedule object."""

    sch.app = app
    sch.nowfun = nowfun
    return sch


def cron_expr_to_celery_schedule(expr: str, *, app: Any, timezone_name: str | None) -> Any:
    """Map one stored cron expression to Celery schedule object."""

    # Import lazily so API processes without celery installed stay import-light.
    from celery.schedules import crontab
    from celery.schedules import schedule as interval_schedule

    trimmed = expr.strip()
    if not trimmed:
        raise ValueError("empty cron expression")

    tz_name = timezone_name.strip() if isinstance(timezone_name, str) and timezone_name.strip() else "Asia/Shanghai"
    parts = trimmed.split()

    def _now_in_job_tz() -> datetime:
        from zoneinfo import ZoneInfo

        return datetime.now(tz=ZoneInfo(tz_name))

    try:
        if len(parts) == 6:
            sec, mn, hh, dom, mon, dow = parts
            m_sec = _SECOND_STEP.match(sec)
            if m_sec is not None:
                seconds = int(m_sec.group(1))
                if seconds > 0 and _all_star((mn, hh, dom, mon, dow)):
                    sch = interval_schedule(
                        timedelta(seconds=seconds),
                        nowfun=_now_in_job_tz,
                        app=app,
                    )
                    return sch

            unix_five = " ".join(parts[1:6])
            sch_cr = crontab.from_string(unix_five)
            return _attach_app_nowfun(sch_cr, app=app, nowfun=_now_in_job_tz)

        if len(parts) == 5:
            sch_cr = crontab.from_string(trimmed)
            return _attach_app_nowfun(sch_cr, app=app, nowfun=_now_in_job_tz)

    except Exception as exc:  # cronfield / split errors
        raise ValueError(str(exc).strip() or "invalid cron expression") from exc

    raise ValueError(f"cron must have 5 or 6 space-separated fields, got {len(parts)}")
