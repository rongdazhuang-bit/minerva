"""Tests for agent overview daily token usage aggregation."""

from __future__ import annotations

from datetime import date, datetime, timezone

from app.agent.service.overview_usage_daily_stats import (
    DAY_COUNT,
    build_day_window,
    extract_usage_series_counts,
    merge_sparse_daily_usage,
)
from zoneinfo import ZoneInfo


def test_extract_usage_series_counts_reads_standard_and_details() -> None:
    """Usage document maps to four chart series keys."""

    counts = extract_usage_series_counts(
        {
            "prompt_tokens": 100,
            "completion_tokens": 40,
            "total_tokens": 140,
            "details": {"cached_tokens": 12, "reasoning_tokens": 8},
        }
    )
    assert counts == {
        "prompt_tokens": 100,
        "completion_tokens": 40,
        "cached_tokens": 12,
        "reasoning_tokens": 8,
    }


def test_merge_sparse_daily_usage_fills_missing_days() -> None:
    """Sparse rows expand to fixed day list with zero-filled gaps."""

    dates = [date(2026, 5, 24), date(2026, 5, 25), date(2026, 5, 26)]
    sparse = [
        (
            date(2026, 5, 24),
            {
                "prompt_tokens": 10,
                "completion_tokens": 5,
                "cached_tokens": 1,
                "reasoning_tokens": 0,
            },
        ),
        (
            date(2026, 5, 26),
            {
                "prompt_tokens": 3,
                "completion_tokens": 2,
                "cached_tokens": 0,
                "reasoning_tokens": 4,
            },
        ),
    ]
    items = merge_sparse_daily_usage(dates, sparse)
    assert len(items) == 3
    assert items[0].prompt_tokens == 10
    assert items[1].prompt_tokens == 0
    assert items[2].reasoning_tokens == 4


def test_build_day_window_returns_seven_days() -> None:
    """Overview chart window length matches ``DAY_COUNT``."""

    zone = ZoneInfo("UTC")
    now = datetime(2026, 5, 26, 15, 0, tzinfo=timezone.utc)
    dates_asc, start_local, end_exclusive = build_day_window(now=now, zone=zone)
    assert len(dates_asc) == DAY_COUNT
    assert dates_asc[0] == date(2026, 5, 20)
    assert dates_asc[-1] == date(2026, 5, 26)
    assert start_local <= now < end_exclusive
