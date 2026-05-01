"""Tests for Postgres beat cron → Celery schedule mapping."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.sys.celery.beat.cron_schedule import cron_expr_to_celery_schedule


@pytest.fixture
def mock_app() -> MagicMock:
    """Provides a fake Celery app instance for schedule objects."""

    return MagicMock(name="celery_app")


def test_six_field_every_n_seconds_uses_interval_schedule(mock_app: MagicMock) -> None:
    """Six-field ``*/N * * * * *`` should map to ``schedule`` with ``timedelta``."""

    from celery.schedules import schedule as interval_schedule

    sch = cron_expr_to_celery_schedule("*/5 * * * * *", app=mock_app, timezone_name="UTC")
    assert isinstance(sch, interval_schedule)
    assert sch.run_every.total_seconds() == 5


def test_five_field_uses_crontab(mock_app: MagicMock) -> None:
    """Standard five-field cron uses Celery ``crontab``."""

    from celery.schedules import crontab

    sch = cron_expr_to_celery_schedule("0 8 * * *", app=mock_app, timezone_name="Asia/Shanghai")
    assert isinstance(sch, crontab)


def test_six_field_non_interval_drops_second_field_for_crontab(mock_app: MagicMock) -> None:
    """Non-trivial six-field expressions fall back to minute-first five-field crontab."""

    from celery.schedules import crontab

    sch = cron_expr_to_celery_schedule("0 */5 * * * *", app=mock_app, timezone_name="UTC")
    assert isinstance(sch, crontab)


def test_invalid_field_count_raises(mock_app: MagicMock) -> None:
    """Four-field expressions should be rejected."""

    with pytest.raises(ValueError, match="5 or 6"):
        cron_expr_to_celery_schedule("* * * *", app=mock_app, timezone_name="UTC")
