"""Tests for datetime tool answer formatting."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import patch

from app.agent.capabilities.datetime.answer import format_datetime_answer
from app.agent.capabilities.datetime.tools import get_system_datetime


def test_format_datetime_answer_date_only() -> None:
    """Date-focused questions return date and weekday."""

    raw = json.dumps(
        {"iso": "2026-05-17T10:30:00+08:00", "timezone": "local", "unix": 0},
        ensure_ascii=False,
    )
    text = format_datetime_answer(raw, "今天是几号")
    assert "2026年5月17日" in text
    assert "星期" in text


def test_get_system_datetime_local_json() -> None:
    """Tool returns parseable JSON with iso and timezone keys."""

    fixed = datetime(2026, 5, 17, 12, 0, 0).astimezone()
    with patch("app.agent.capabilities.datetime.tools.datetime") as mock_dt:
        mock_dt.now.return_value = fixed
        raw = get_system_datetime.invoke({"timezone": "LOCAL"})
    payload = json.loads(raw)
    assert "iso" in payload
    assert payload["timezone"] == "local"
