"""Async persistence helpers for document translation jobs and segments."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.translate.domain.constants import DOC_TRANSLATE_LIST_MAX_LIMIT
from app.translate.domain.db.models import DocTranslateJob, DocTranslateSegment


def encode_doc_translate_job_cursor(updated_at: datetime, job_id: uuid.UUID) -> str:
    """Encode ``(update_at, id)`` for keyset pagination (newest-first list)."""

    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=UTC)
    return f"{ts.isoformat()}|{job_id}"


def decode_doc_translate_job_cursor(raw: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor produced by ``encode_doc_translate_job_cursor``."""

    marker = raw.rfind("|")
    if marker <= 0:
        raise ValueError("invalid doc translate job cursor")
    ts = datetime.fromisoformat(raw[:marker])
    jid = uuid.UUID(raw[marker + 1 :])
    return ts, jid


async def create_doc_translate_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID | None,
    title: str | None,
    file_name: str | None,
    file_ext: str,
    source_lang: str,
    target_lang: str,
    model_id: uuid.UUID,
    status: str,
    source_object_key: str,
) -> DocTranslateJob:
    """Insert one new translation job row."""

    now = datetime.now(UTC)
    row = DocTranslateJob(
        workspace_id=workspace_id,
        created_by=created_by,
        title=title,
        file_name=file_name,
        file_ext=file_ext,
        source_lang=source_lang,
        target_lang=target_lang,
        model_id=model_id,
        status=status,
        source_object_key=source_object_key,
        progress=0,
        segment_total=0,
        segment_done=0,
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await session.flush()
    return row


async def get_doc_translate_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> DocTranslateJob | None:
    """Load one job scoped to a workspace."""

    stmt = select(DocTranslateJob).where(
        DocTranslateJob.id == job_id,
        DocTranslateJob.workspace_id == workspace_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_doc_translate_jobs_recent(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    cursor_update_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
) -> tuple[list[DocTranslateJob], bool]:
    """Return recent jobs newest-first with keyset cursor pagination."""

    cap = max(1, min(limit, DOC_TRANSLATE_LIST_MAX_LIMIT))
    sort_ts = func.coalesce(DocTranslateJob.update_at, DocTranslateJob.create_at)
    stmt = select(DocTranslateJob).where(DocTranslateJob.workspace_id == workspace_id)
    if cursor_update_at is not None and cursor_id is not None:
        stmt = stmt.where(
            or_(
                sort_ts < cursor_update_at,
                and_(sort_ts == cursor_update_at, DocTranslateJob.id < cursor_id),
            )
        )
    stmt = stmt.order_by(desc(sort_ts), desc(DocTranslateJob.id)).limit(cap + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    has_more = len(rows) > cap
    return rows[:cap], has_more


async def list_doc_translate_jobs_filtered(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
    file_name: str | None = None,
    status: str | None = None,
    create_at_start: datetime | None = None,
    create_at_end: datetime | None = None,
) -> tuple[list[DocTranslateJob], int]:
    """Return jobs newest-first with offset pagination and optional filters."""

    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    sort_ts = func.coalesce(DocTranslateJob.update_at, DocTranslateJob.create_at)
    stmt = select(DocTranslateJob).where(DocTranslateJob.workspace_id == workspace_id)
    if file_name is not None and file_name.strip() != "":
        stmt = stmt.where(DocTranslateJob.file_name.ilike(f"%{file_name.strip()}%"))
    if status is not None and status.strip() != "":
        stmt = stmt.where(DocTranslateJob.status == status.strip())
    if create_at_start is not None:
        stmt = stmt.where(DocTranslateJob.create_at >= create_at_start)
    if create_at_end is not None:
        stmt = stmt.where(DocTranslateJob.create_at <= create_at_end)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = int(await session.scalar(total_stmt) or 0)
    rows = (
        await session.execute(
            stmt.order_by(desc(sort_ts), desc(DocTranslateJob.id))
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return list(rows), total


async def update_doc_translate_job(
    session: AsyncSession,
    *,
    job_id: uuid.UUID,
    workspace_id: uuid.UUID,
    **fields: Any,
) -> None:
    """Patch whitelisted job columns and bump ``update_at``."""

    allowed = {
        "title",
        "status",
        "result_object_key",
        "ocr_file_id",
        "progress",
        "segment_total",
        "segment_done",
        "error_code",
        "error_message",
    }
    values = {k: v for k, v in fields.items() if k in allowed}
    values["update_at"] = datetime.now(UTC)
    if not values:
        return
    await session.execute(
        update(DocTranslateJob)
        .where(
            DocTranslateJob.id == job_id,
            DocTranslateJob.workspace_id == workspace_id,
        )
        .values(**values)
    )
    await session.flush()


async def bulk_insert_segments(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    segments: list[dict[str, Any]],
) -> None:
    """Insert paragraph rows in one flush (``segments`` dict keys: seq, source_text, status, anchor_json)."""

    for item in segments:
        session.add(
            DocTranslateSegment(
                job_id=job_id,
                workspace_id=workspace_id,
                seq=int(item["seq"]),
                source_text=str(item["source_text"]),
                translated_text=item.get("translated_text"),
                status=str(item.get("status", "PENDING")),
                anchor_json=item.get("anchor_json"),
                error_message=item.get("error_message"),
            )
        )
    await session.flush()


async def list_segments_by_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    limit: int,
) -> list[DocTranslateSegment]:
    """Return segments ordered by ``seq`` ascending."""

    stmt = (
        select(DocTranslateSegment)
        .where(
            DocTranslateSegment.job_id == job_id,
            DocTranslateSegment.workspace_id == workspace_id,
        )
        .order_by(DocTranslateSegment.seq.asc())
        .limit(limit)
    )
    return list((await session.execute(stmt)).scalars().all())


async def update_segment_translation(
    session: AsyncSession,
    *,
    segment_id: uuid.UUID,
    workspace_id: uuid.UUID,
    translated_text: str | None,
    status: str,
    error_message: str | None = None,
) -> None:
    """Update one segment after LLM translation."""

    await session.execute(
        update(DocTranslateSegment)
        .where(
            DocTranslateSegment.id == segment_id,
            DocTranslateSegment.workspace_id == workspace_id,
        )
        .values(
            translated_text=translated_text,
            status=status,
            error_message=error_message,
        )
    )
    await session.flush()


async def delete_doc_translate_job_dependents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> bool:
    """Delete segments then job; returns False when the job row is missing."""

    row = await get_doc_translate_job(session, workspace_id=workspace_id, job_id=job_id)
    if row is None:
        return False
    await session.execute(
        delete(DocTranslateSegment).where(
            DocTranslateSegment.job_id == job_id,
            DocTranslateSegment.workspace_id == workspace_id,
        )
    )
    await session.delete(row)
    await session.flush()
    return True
