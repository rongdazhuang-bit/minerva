"""Workspace endpoints for file OCR task APIs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.domain.identity.models import User
from app.file_ocr.api.schemas import (
    OcrFileOverviewStatsOut,
)
from app.file_ocr.domain.db.models import OcrFile

file_router = APIRouter(prefix="/workspaces/{workspace_id}/ocr-files", tags=["ocr-files"])


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
