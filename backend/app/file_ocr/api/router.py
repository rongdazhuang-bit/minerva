"""Workspace endpoints for file OCR task APIs."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.core.domain.identity.models import User
from app.exceptions import AppError
from app.file_ocr.api.schemas import OcrFileBatchCreateOut
from app.file_ocr.api.schemas import (
    OcrFileCreateIn,
    OcrFileListItemOut,
    OcrFileListPageOut,
    OcrFileLogItemOut,
    OcrFileLogListPageOut,
    OcrFileMarkdownPagesOut,
    OcrFileOverviewLogDailyStatsOut,
    OcrFileOverviewStatsOut,
)
from app.file_ocr.domain.db.models import OcrFile
from app.file_ocr.domain.db.models_log import OcrFileLog
from app.file_ocr.service.markdown_pages import get_ocr_file_markdown_pages
from app.file_ocr.service.overview_log_daily_stats import compute_overview_log_daily_stats
from app.file_ocr.service.result_row_cleanup import delete_ocr_file_engine_result_rows
from app.pagination import DEFAULT_PAGE_SIZE

file_router = APIRouter(prefix="/workspaces/{workspace_id}/ocr-files", tags=["ocr-files"])


def _to_list_item(row: OcrFile) -> OcrFileListItemOut:
    """Project ORM row into API list item schema."""

    return OcrFileListItemOut.model_validate(row, from_attributes=True)


@file_router.get("", response_model=OcrFileListPageOut)
async def list_ocr_files(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    file_name: str | None = Query(default=None),
    ocr_type: str | None = Query(default=None),
    status: str | None = Query(default=None),
    create_at_start: datetime | None = Query(default=None),
    create_at_end: datetime | None = Query(default=None),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileListPageOut:
    """Return paginated OCR task rows with optional query filters."""

    stmt = select(OcrFile).where(OcrFile.workspace_id == workspace_id)
    if file_name is not None and file_name.strip() != "":
        stmt = stmt.where(OcrFile.file_name.ilike(f"%{file_name.strip()}%"))
    if ocr_type is not None and ocr_type.strip() != "":
        stmt = stmt.where(OcrFile.ocr_type == ocr_type.strip())
    if status is not None and status.strip() != "":
        stmt = stmt.where(OcrFile.status == status.strip())
    if create_at_start is not None:
        stmt = stmt.where(OcrFile.create_at >= create_at_start)
    if create_at_end is not None:
        stmt = stmt.where(OcrFile.create_at <= create_at_end)

    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(total_stmt)
    rows = (
        await session.execute(
            stmt.order_by(OcrFile.create_at.desc(), OcrFile.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return OcrFileListPageOut(items=[_to_list_item(r) for r in rows], total=int(total or 0))


@file_router.post("", response_model=OcrFileBatchCreateOut, status_code=status.HTTP_201_CREATED)
async def create_ocr_files(
    workspace_id: uuid.UUID,
    body: OcrFileCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileBatchCreateOut:
    """Create INIT OCR task rows after source files were uploaded to S3.

    Initializes ``create_at`` and ``update_at`` to the same UTC instant so list
    ordering and UI columns are populated even when the DB column has no default.
    """

    now = datetime.now(UTC)
    rows: list[OcrFile] = []
    for file in body.files:
        row = OcrFile(
            workspace_id=workspace_id,
            file_name=file.file_name.strip(),
            file_size=file.file_size,
            object_key=file.object_key.strip(),
            ocr_type=body.ocr_type,
            status="INIT",
            page_count=None,
            create_at=now,
            update_at=now,
        )
        session.add(row)
        rows.append(row)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return OcrFileBatchCreateOut(items=[_to_list_item(r) for r in rows], total=len(rows))


@file_router.get("/overview-stats", response_model=OcrFileOverviewStatsOut)
async def get_ocr_file_overview_stats(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileOverviewStatsOut:
    """Return grouped OCR file-task counts for INIT/PROCESS/SUCCESS/FAILED statuses."""

    stmt = select(
        func.coalesce(
            func.sum(case((OcrFile.status == "INIT", 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((OcrFile.status == "PROCESS", 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((OcrFile.status == "SUCCESS", 1), else_=0)),
            0,
        ),
        func.coalesce(
            func.sum(case((OcrFile.status == "FAILED", 1), else_=0)),
            0,
        ),
    ).where(OcrFile.workspace_id == workspace_id)
    row = (await session.execute(stmt)).one()
    return OcrFileOverviewStatsOut(
        init_count=int(row[0] or 0),
        process_count=int(row[1] or 0),
        success_count=int(row[2] or 0),
        failed_count=int(row[3] or 0),
    )


@file_router.get("/overview-log-daily-stats", response_model=OcrFileOverviewLogDailyStatsOut)
async def get_ocr_file_overview_log_daily_stats(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileOverviewLogDailyStatsOut:
    """Return last 30 local days of OCR log success/fail counts by engine."""

    return await compute_overview_log_daily_stats(session, workspace_id)


def _to_log_item(row: OcrFileLog) -> OcrFileLogItemOut:
    """Map ORM ``start_at``/``finish_at`` to API ``create_at``/``update_at`` for list display."""

    return OcrFileLogItemOut(
        id=row.id,
        create_at=row.start_at,
        update_at=row.finish_at,
        status=row.status,
        remark=row.remark,
    )


@file_router.get("/{ocr_file_id}/logs", response_model=OcrFileLogListPageOut)
async def list_ocr_file_logs(
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileLogListPageOut:
    """Return paginated OCR run logs for one task in the workspace."""

    exists = await session.scalar(
        select(OcrFile.id).where(
            OcrFile.id == ocr_file_id,
            OcrFile.workspace_id == workspace_id,
        )
    )
    if exists is None:
        raise AppError("ocr_file.not_found", "OCR task not found", 404)
    stmt = select(OcrFileLog).where(
        OcrFileLog.ocr_file_id == ocr_file_id,
        OcrFileLog.workspace_id == workspace_id,
    )
    total_stmt = select(func.count()).select_from(stmt.subquery())
    total = await session.scalar(total_stmt)
    rows = (
        await session.execute(
            stmt.order_by(OcrFileLog.start_at.desc(), OcrFileLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()
    return OcrFileLogListPageOut(items=[_to_log_item(r) for r in rows], total=int(total or 0))


@file_router.get("/{ocr_file_id}/markdown-pages", response_model=OcrFileMarkdownPagesOut)
async def get_ocr_file_markdown_pages_endpoint(
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileMarkdownPagesOut:
    """Return per-page markdown and parsed image maps for a SUCCESS OCR task."""

    return await get_ocr_file_markdown_pages(
        session=session, workspace_id=workspace_id, ocr_file_id=ocr_file_id
    )


@file_router.post("/{ocr_file_id}/retry", response_model=OcrFileListItemOut)
async def retry_ocr_file(
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrFileListItemOut:
    """Reset a finished or failed task to INIT so the OCR worker can pick it up again."""

    result = await session.execute(
        select(OcrFile).where(
            OcrFile.id == ocr_file_id,
            OcrFile.workspace_id == workspace_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("ocr_file.not_found", "OCR task not found", 404)
    if row.status == "PROCESS":
        raise AppError(
            "ocr_file.retry_conflict",
            "Cannot retry while the task is PROCESS; cancel or wait for completion",
            409,
        )
    await delete_ocr_file_engine_result_rows(
        session,
        workspace_id=workspace_id,
        file_id=ocr_file_id,
        ocr_type=row.ocr_type,
    )
    now = datetime.now(UTC)
    row.status = "INIT"
    row.page_count = None
    row.remark = None
    row.update_at = now
    await session.commit()
    await session.refresh(row)
    return _to_list_item(row)


@file_router.delete("/{ocr_file_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_ocr_file(
    workspace_id: uuid.UUID,
    ocr_file_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Delete one OCR task row in the current workspace."""

    result = await session.execute(
        select(OcrFile).where(
            OcrFile.id == ocr_file_id,
            OcrFile.workspace_id == workspace_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AppError("ocr_file.not_found", "OCR task not found", 404)
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
