"""Unit tests for OCR overview daily log aggregation helpers."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
import uuid
from unittest.mock import patch

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.infrastructure.db.session import engine
from app.dependencies import get_db
from app.file_ocr.service.overview_log_daily_stats import (
    DAY_COUNT,
    build_day_window,
    compute_overview_log_daily_stats,
    merge_sparse_daily_counts,
    resolve_stats_iana_zone,
)
from app.main import app
from tests.test_file_ocr_api import _ensure_ocr_file_columns, _workspace_id_from_access_token


def test_build_day_window_returns_thirty_ascending_dates() -> None:
    """Pinned ``now`` should yield 30 consecutive local days ending on that calendar day."""

    zone = ZoneInfo("UTC")
    now = datetime(2026, 5, 14, 15, 30, tzinfo=zone)
    dates_asc, start_local, end_excl = build_day_window(now=now, zone=zone)
    assert len(dates_asc) == DAY_COUNT
    assert dates_asc[0] == date(2026, 4, 15)
    assert dates_asc[-1] == date(2026, 5, 14)
    assert dates_asc == sorted(dates_asc)
    assert start_local == datetime(2026, 4, 15, 0, 0, tzinfo=zone)
    assert end_excl == datetime(2026, 5, 15, 0, 0, tzinfo=zone)


def test_merge_sparse_fills_zeros_and_maps_types() -> None:
    """Sparse SQL groups should expand into ordered daily items with correct keys."""

    d0 = date(2026, 5, 1)
    dates = [d0 + timedelta(days=i) for i in range(5)]
    sparse = [
        (d0, "PADDLE_OCR", "SUCCESS", 2),
        (d0, "MINERU", "FAILED", 1),
        (d0 + timedelta(days=2), "PADDLE_OCR", "FAILED", 3),
    ]
    items = merge_sparse_daily_counts(dates, sparse)
    assert len(items) == 5
    assert items[0].date == "2026-05-01"
    assert items[0].paddle_success == 2
    assert items[0].mineru_failed == 1
    assert items[1].paddle_success == 0
    assert items[2].paddle_failed == 3


@pytest.mark.asyncio
async def test_get_overview_log_daily_stats_endpoint_shape() -> None:
    """Authenticated GET should return exactly ``DAY_COUNT`` dated buckets."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-daily-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        resp = await ac.get(
            f"/workspaces/{workspace_id}/ocr-files/overview-log-daily-stats",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body["items"]) == DAY_COUNT
        for row in body["items"]:
            assert "date" in row
            assert row["paddle_success"] >= 0


@pytest.mark.asyncio
async def test_compute_counts_inserted_logs_with_fixed_clock() -> None:
    """Service layer should count inserted SUCCESS rows on a pinned ``now`` day."""

    await _ensure_ocr_file_columns()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        email = f"fo-daily-db-{uuid.uuid4().hex}@example.com"
        reg = await ac.post("/auth/register", json={"email": email, "password": "secret1234"})
        assert reg.status_code == 201, reg.text
        token = reg.json()["access_token"]
        workspace_id = _workspace_id_from_access_token(token)
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "ocr_type": "PADDLE_OCR",
            "files": [
                {"file_name": "a.pdf", "file_size": 10, "object_key": "ocr_file/2026/05/daily.pdf"},
            ],
        }
        create = await ac.post(f"/workspaces/{workspace_id}/ocr-files", headers=headers, json=payload)
        assert create.status_code == 201, create.text
        ocr_id = create.json()["items"][0]["id"]

    fixed_now = datetime(2026, 5, 14, 12, 0, 0, tzinfo=UTC)
    log_ts = datetime(2026, 5, 14, 8, 0, 0, tzinfo=UTC)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO ocr_file_log "
                "(id, workspace_id, ocr_file_id, ocr_type, status, page_count, remark, start_at, finish_at) "
                "VALUES (gen_random_uuid(), CAST(:wid AS uuid), CAST(:fid AS uuid), "
                "'PADDLE_OCR', 'SUCCESS', NULL, NULL, CAST(:ts AS timestamptz), CAST(:ts AS timestamptz))"
            ),
            {"wid": workspace_id, "fid": ocr_id, "ts": log_ts},
        )

    async for session in get_db():
        assert isinstance(session, AsyncSession)
        with patch(
            "app.file_ocr.service.overview_log_daily_stats.resolve_stats_iana_zone",
            return_value="UTC",
        ):
            out = await compute_overview_log_daily_stats(
                session,
                uuid.UUID(workspace_id),
                now=fixed_now,
            )
        break

    last = out.items[-1]
    assert last.date == "2026-05-14"
    assert last.paddle_success == 1

    async with engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM ocr_file_log WHERE ocr_file_id = CAST(:fid AS uuid)"),
            {"fid": ocr_id},
        )


def test_resolve_stats_iana_zone_invalid_tz_env_falls_back() -> None:
    """Unknown ``TZ`` values should not crash and should fall back to UTC."""

    with patch.dict("os.environ", {"TZ": "NotARealZoneName123"}, clear=False):
        assert resolve_stats_iana_zone() == "UTC"
