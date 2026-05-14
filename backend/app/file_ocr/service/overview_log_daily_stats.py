"""Aggregate ``ocr_file_log`` into fixed 30-day daily series for the overview chart."""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta

from sqlalchemy import Date, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.file_ocr.api.schemas import OcrFileOverviewLogDailyStatItemOut, OcrFileOverviewLogDailyStatsOut
from app.file_ocr.constants import FILE_OCR_LOG_STATUS_FAILED, FILE_OCR_LOG_STATUS_SUCCESS
from app.file_ocr.domain.db.models_log import OcrFileLog

DAY_COUNT = 30


def resolve_stats_iana_zone() -> str:
    """Pick the IANA zone used to bucket ``start_at`` into calendar days.

    Prefer the ``TZ`` environment variable when it names a valid IANA zone;
    otherwise fall back to ``UTC`` so CI and laptops behave deterministically.
    """

    raw = os.environ.get("TZ")
    if raw is None or not str(raw).strip():
        return "UTC"
    candidate = str(raw).strip()
    try:
        ZoneInfo(candidate)
    except ZoneInfoNotFoundError:
        return "UTC"
    return candidate


def build_day_window(
    *,
    now: datetime,
    zone: ZoneInfo,
) -> tuple[list[date], datetime, datetime]:
    """Build the inclusive local date list and the UTC half-open window for SQL filters.

    Returns ``dates_asc`` (oldest first, length ``DAY_COUNT``), local midnight at
    the first day, and local midnight **after** the last day (exclusive upper bound).
    """

    if now.tzinfo is None:
        now = now.replace(tzinfo=zone)
    now_local = now.astimezone(zone)
    today = now_local.date()
    dates_asc = [today - timedelta(days=DAY_COUNT - 1 - i) for i in range(DAY_COUNT)]
    start_local = datetime.combine(dates_asc[0], time.min, tzinfo=zone)
    end_local_exclusive = datetime.combine(dates_asc[-1] + timedelta(days=1), time.min, tzinfo=zone)
    return dates_asc, start_local, end_local_exclusive


def merge_sparse_daily_counts(
    dates_asc: Sequence[date],
    sparse_rows: Sequence[tuple[date, str, str, int]],
) -> list[OcrFileOverviewLogDailyStatItemOut]:
    """Fill missing days with zeros and map SQL groups into the four API counters."""

    counts: dict[date, dict[str, int]] = {
        d: {
            "paddle_success": 0,
            "paddle_failed": 0,
            "mineru_success": 0,
            "mineru_failed": 0,
        }
        for d in dates_asc
    }
    for log_day, ocr_type, status, cnt in sparse_rows:
        if log_day not in counts:
            continue
        key = _counter_key(ocr_type, status)
        if key is None:
            continue
        counts[log_day][key] += int(cnt)
    out: list[OcrFileOverviewLogDailyStatItemOut] = []
    for d in dates_asc:
        row = counts[d]
        out.append(
            OcrFileOverviewLogDailyStatItemOut(
                date=d.isoformat(),
                paddle_success=row["paddle_success"],
                paddle_failed=row["paddle_failed"],
                mineru_success=row["mineru_success"],
                mineru_failed=row["mineru_failed"],
            )
        )
    return out


def _counter_key(ocr_type: str, status: str) -> str | None:
    """Map ``(ocr_type, status)`` to one of the four series keys, or ``None`` to skip."""

    if status not in (FILE_OCR_LOG_STATUS_SUCCESS, FILE_OCR_LOG_STATUS_FAILED):
        return None
    if ocr_type == "PADDLE_OCR":
        return "paddle_success" if status == FILE_OCR_LOG_STATUS_SUCCESS else "paddle_failed"
    if ocr_type == "MINERU":
        return "mineru_success" if status == FILE_OCR_LOG_STATUS_SUCCESS else "mineru_failed"
    return None


async def compute_overview_log_daily_stats(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> OcrFileOverviewLogDailyStatsOut:
    """Return ``DAY_COUNT`` ascending local days of OCR log success/fail counts."""

    tz_name = resolve_stats_iana_zone()
    zone = ZoneInfo(tz_name)
    if now is None:
        now = datetime.now(zone)
    dates_asc, start_local, end_local_exclusive = build_day_window(now=now, zone=zone)

    day_col = cast(func.timezone(tz_name, OcrFileLog.start_at), Date).label("log_day")
    stmt = (
        select(day_col, OcrFileLog.ocr_type, OcrFileLog.status, func.count().label("cnt"))
        .where(
            OcrFileLog.workspace_id == workspace_id,
            OcrFileLog.start_at >= start_local,
            OcrFileLog.start_at < end_local_exclusive,
            OcrFileLog.status.in_((FILE_OCR_LOG_STATUS_SUCCESS, FILE_OCR_LOG_STATUS_FAILED)),
        )
        .group_by(day_col, OcrFileLog.ocr_type, OcrFileLog.status)
    )
    result = await session.execute(stmt)
    sparse: list[tuple[date, str, str, int]] = []
    for log_day, ocr_type, status, cnt in result.all():
        if log_day is None:
            continue
        sparse.append((log_day, str(ocr_type), str(status), int(cnt or 0)))

    items = merge_sparse_daily_counts(dates_asc, sparse)
    return OcrFileOverviewLogDailyStatsOut(items=items)
