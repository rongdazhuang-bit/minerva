"""Scan ``ocr_file`` INIT rows and dispatch work to per-engine strategies."""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.file_ocr.constants import (
    FILE_OCR_LOG_STATUS_FAILED,
    FILE_OCR_LOG_STATUS_RUNNING,
    FILE_OCR_LOG_STATUS_SUCCESS,
    FILE_OCR_REMARK_MAX_LEN,
    FILE_OCR_SCAN_BATCH_SIZE,
    FILE_OCR_SUPPORTED_SCAN_OCR_TYPES,
)
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_log import OcrFileLog
from app.file_ocr.service.ocr_tool_pick import select_default_ocr_tool
from app.file_ocr.service.strategies.registry import get_file_ocr_strategy

_LOGGER = logging.getLogger(__name__)


def _utc_now() -> datetime:
    """Return timezone-aware UTC ``datetime`` for status transitions."""

    return datetime.now(UTC)


def _truncate_remark(text: str) -> str:
    """Bound OCR failure text to keep ``ocr_file.remark`` rows worker-safe."""

    t = text.strip()
    if len(t) <= FILE_OCR_REMARK_MAX_LEN:
        return t
    return t[: FILE_OCR_REMARK_MAX_LEN - 1] + "…"


def _finalize_ocr_file_log(
    run_log: OcrFileLog,
    *,
    status: str,
    remark: str | None = None,
    page_count: int | None = None,
) -> None:
    """Set terminal fields on one ``OcrFileLog`` row inside the active transaction."""

    now = _utc_now()
    run_log.status = status
    run_log.finish_at = now
    if status == FILE_OCR_LOG_STATUS_SUCCESS:
        run_log.page_count = page_count
        run_log.remark = None
    else:
        run_log.page_count = None
        run_log.remark = _truncate_remark(remark) if remark else None


async def _claim_init_batch(session: AsyncSession) -> list[uuid.UUID]:
    """Lock and flip a bounded batch of INIT rows to PROCESS inside one transaction."""

    async with session.begin():
        stmt = (
            select(OcrFile)
            .where(
                OcrFile.status == "INIT",
                OcrFile.ocr_type.in_(FILE_OCR_SUPPORTED_SCAN_OCR_TYPES),
            )
            .order_by(OcrFile.create_at.asc().nulls_last(), OcrFile.id.asc())
            .limit(FILE_OCR_SCAN_BATCH_SIZE)
            .with_for_update(skip_locked=True)
        )
        result = await session.execute(stmt)
        rows = list(result.scalars().all())
        now = _utc_now()
        for row in rows:
            row.status = "PROCESS"
            row.update_at = now
        return [r.id for r in rows]


async def _process_one_claimed(session: AsyncSession, *, ocr_file_id: uuid.UUID) -> str:
    """Process a single claimed id; returns a coarse outcome label for summaries."""

    async with session.begin():
        row = await session.get(OcrFile, ocr_file_id)
        if row is None:
            return "missing"
        if row.status != "PROCESS":
            return "skip"
        started = _utc_now()
        run_log = OcrFileLog(
            id=uuid.uuid4(),
            workspace_id=row.workspace_id,
            ocr_file_id=row.id,
            ocr_type=row.ocr_type,
            status=FILE_OCR_LOG_STATUS_RUNNING,
            page_count=None,
            remark=None,
            start_at=started,
            finish_at=None,
        )
        session.add(run_log)
        await session.flush()
        tool = await select_default_ocr_tool(
            session,
            workspace_id=row.workspace_id,
            ocr_type=row.ocr_type,
        )
        if tool is None:
            row.status = "FAILED"
            row.remark = _truncate_remark("file_ocr:no_sys_ocr_tool")
            row.update_at = _utc_now()
            _finalize_ocr_file_log(
                run_log,
                status=FILE_OCR_LOG_STATUS_FAILED,
                remark=row.remark,
            )
            return "no_tool"
        if not (tool.url or "").strip():
            row.status = "FAILED"
            row.remark = _truncate_remark("file_ocr:empty_tool_url")
            row.update_at = _utc_now()
            _finalize_ocr_file_log(
                run_log,
                status=FILE_OCR_LOG_STATUS_FAILED,
                remark=row.remark,
            )
            return "bad_tool"
        strategy = get_file_ocr_strategy(row.ocr_type)
        try:
            await strategy.process(session=session, ocr_file=row, tool=tool)
        except Exception as exc:  # noqa: BLE001 - vendor/S3 failures become FAILED rows.
            _LOGGER.exception("file_ocr scan failed for ocr_file_id=%s", ocr_file_id)
            row.status = "FAILED"
            row.remark = _truncate_remark(f"file_ocr:{exc.__class__.__name__}:{exc}")
            row.update_at = _utc_now()
            _finalize_ocr_file_log(
                run_log,
                status=FILE_OCR_LOG_STATUS_FAILED,
                remark=row.remark,
            )
            return "error"
        _finalize_ocr_file_log(
            run_log,
            status=FILE_OCR_LOG_STATUS_SUCCESS,
            page_count=row.page_count,
        )
        return "ok"


async def run_file_ocr_scan_tick(session: AsyncSession) -> dict[str, Any]:
    """Claim INIT rows once, then process each id in its own transaction."""

    claimed_ids = await _claim_init_batch(session)
    summary: dict[str, Any] = {
        "claimed": len(claimed_ids),
        "ok": 0,
        "failed": 0,
        "skipped": 0,
    }
    for oid in claimed_ids:
        outcome = await _process_one_claimed(session, ocr_file_id=oid)
        if outcome == "ok":
            summary["ok"] += 1
        elif outcome in {"missing", "skip"}:
            summary["skipped"] += 1
        else:
            summary["failed"] += 1
    _LOGGER.info(
        "file_ocr scan tick finished %s",
        summary,
        extra={"event": "ocr.scan.initialized", "file_count": summary["claimed"]},
    )
    return summary
