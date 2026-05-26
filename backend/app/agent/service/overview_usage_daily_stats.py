"""Aggregate ``agent_run.usage_json`` into fixed 7-day daily series for overview chart."""

from __future__ import annotations

import os
import uuid
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.agent.api.v2.schemas import AgentOverviewUsageDailyStatItemOut, AgentOverviewUsageDailyStatsOut
from app.agent.domain.db.models import AgentRun
from app.agent.infrastructure.openai_usage import usage_document_flat

DAY_COUNT = 7

_TOKEN_SERIES_KEYS = (
    "prompt_tokens",
    "completion_tokens",
    "cached_tokens",
    "reasoning_tokens",
)


def resolve_stats_iana_zone() -> str:
    """Pick the IANA zone used to bucket run timestamps into calendar days."""

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
    """Build ascending local dates and UTC half-open window for SQL filters."""

    if now.tzinfo is None:
        now = now.replace(tzinfo=zone)
    now_local = now.astimezone(zone)
    today = now_local.date()
    dates_asc = [today - timedelta(days=DAY_COUNT - 1 - i) for i in range(DAY_COUNT)]
    start_local = datetime.combine(dates_asc[0], time.min, tzinfo=zone)
    end_local_exclusive = datetime.combine(dates_asc[-1] + timedelta(days=1), time.min, tzinfo=zone)
    return dates_asc, start_local, end_local_exclusive


def extract_usage_series_counts(usage_json: Any) -> dict[str, int]:
    """Map one run ``usage_json`` document to the four chart series counters."""

    counts = {key: 0 for key in _TOKEN_SERIES_KEYS}
    if not isinstance(usage_json, dict):
        return counts

    flat = usage_document_flat(usage_json)
    counts["prompt_tokens"] = int(flat.get("prompt_tokens", 0))
    counts["completion_tokens"] = int(flat.get("completion_tokens", 0))

    details = usage_json.get("details")
    if isinstance(details, dict):
        cached = details.get("cached_tokens")
        reasoning = details.get("reasoning_tokens")
        if isinstance(cached, (int, float)) and cached >= 0:
            counts["cached_tokens"] = int(cached)
        if isinstance(reasoning, (int, float)) and reasoning >= 0:
            counts["reasoning_tokens"] = int(reasoning)
    return counts


def merge_sparse_daily_usage(
    dates_asc: Sequence[date],
    sparse_rows: Sequence[tuple[date, dict[str, int]]],
) -> list[AgentOverviewUsageDailyStatItemOut]:
    """Fill missing days with zeros and emit API rows in ascending date order."""

    totals: dict[date, dict[str, int]] = {
        d: {key: 0 for key in _TOKEN_SERIES_KEYS} for d in dates_asc
    }
    for usage_day, row_counts in sparse_rows:
        if usage_day not in totals:
            continue
        bucket = totals[usage_day]
        for key in _TOKEN_SERIES_KEYS:
            bucket[key] += int(row_counts.get(key, 0))

    out: list[AgentOverviewUsageDailyStatItemOut] = []
    for d in dates_asc:
        row = totals[d]
        out.append(
            AgentOverviewUsageDailyStatItemOut(
                date=d.isoformat(),
                prompt_tokens=row["prompt_tokens"],
                completion_tokens=row["completion_tokens"],
                cached_tokens=row["cached_tokens"],
                reasoning_tokens=row["reasoning_tokens"],
            )
        )
    return out


async def compute_overview_usage_daily_stats(
    session: AsyncSession,
    workspace_id: uuid.UUID,
    *,
    now: datetime | None = None,
) -> AgentOverviewUsageDailyStatsOut:
    """Return ``DAY_COUNT`` ascending local days of agent token usage by type."""

    tz_name = resolve_stats_iana_zone()
    zone = ZoneInfo(tz_name)
    if now is None:
        now = datetime.now(zone)
    dates_asc, start_local, end_local_exclusive = build_day_window(now=now, zone=zone)

    run_ts = func.coalesce(AgentRun.finished_at, AgentRun.started_at)
    stmt = select(run_ts, AgentRun.usage_json).where(
        AgentRun.workspace_id == workspace_id,
        AgentRun.usage_json.isnot(None),
        run_ts.isnot(None),
        run_ts >= start_local,
        run_ts < end_local_exclusive,
    )
    result = await session.execute(stmt)
    sparse: list[tuple[date, dict[str, int]]] = []
    for run_at, usage_json in result.all():
        if run_at is None:
            continue
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=ZoneInfo("UTC"))
        usage_day = run_at.astimezone(zone).date()
        sparse.append((usage_day, extract_usage_series_counts(usage_json)))

    items = merge_sparse_daily_usage(dates_asc, sparse)
    return AgentOverviewUsageDailyStatsOut(items=items)
