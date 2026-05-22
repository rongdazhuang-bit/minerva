"""Workspace HTTP routes for document translation."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.exceptions import AppError
from app.file_ocr.api.schemas import OcrLayoutPagesOut
from app.pagination import DEFAULT_PAGE_SIZE
from app.s3.service.s3_file_service import S3FileService
from app.translate.api.schemas import (
    DocTranslateJobCreateOut,
    DocTranslateJobDetailOut,
    DocTranslateJobListItemOut,
    DocTranslateJobListOut,
    DocTranslateSegmentGroupOut,
    DocTranslateSegmentListOut,
    DocTranslateSegmentOut,
)
from app.translate.domain.constants import (
    DOC_TRANSLATE_SEGMENTS_MAX_RETURN,
    DOC_TRANSLATE_STATUS_PENDING,
    DOC_TRANSLATE_STATUS_SUCCESS,
)
from app.translate.domain.db.models import DocTranslateJob
from app.translate.infrastructure import repository as translate_repo
from app.translate.service.job_delete import delete_doc_translate_job
from app.translate.service.layout_pages import _segment_page_index
from app.translate.service.layout_pages import get_translate_job_layout_pages
from app.translate.service.job_service import create_job_from_upload
from app.translate.service.translate_dict_seed import ensure_translate_status_dicts

router = APIRouter(prefix="/workspaces/{workspace_id}/translate", tags=["translate"])


def _job_list_item(row: DocTranslateJob) -> DocTranslateJobListItemOut:
    """Map one ORM job row to a list/table API item."""

    return DocTranslateJobListItemOut(
        id=row.id,
        title=row.title,
        file_name=row.file_name,
        file_ext=row.file_ext,
        source_lang=row.source_lang,
        target_lang=row.target_lang,
        source_object_key=row.source_object_key,
        result_object_key=row.result_object_key,
        segment_total=int(row.segment_total or 0),
        segment_done=int(row.segment_done or 0),
        status=row.status,
        progress=int(row.progress or 0),
        create_at=row.create_at,
        update_at=row.update_at,
    )


@router.post("/jobs", response_model=DocTranslateJobCreateOut, status_code=status.HTTP_201_CREATED)
async def create_translate_job(
    workspace_id: uuid.UUID,
    source_lang: str = Form(...),
    target_lang: str = Form(...),
    model_id: uuid.UUID = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> DocTranslateJobCreateOut:
    """Upload a document and enqueue translation."""

    job_id = await create_job_from_upload(
        session,
        workspace_id=workspace_id,
        created_by=user.id,
        file=file,
        source_lang=source_lang,
        target_lang=target_lang,
        model_id=model_id,
    )
    return DocTranslateJobCreateOut(id=job_id, status=DOC_TRANSLATE_STATUS_PENDING)


@router.get("/jobs", response_model=DocTranslateJobListOut)
async def list_translate_jobs(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    file_name: str | None = Query(default=None),
    status: str | None = Query(default=None),
    create_at_start: datetime | None = Query(default=None),
    create_at_end: datetime | None = Query(default=None),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> DocTranslateJobListOut:
    """List translation jobs with offset pagination and optional filters."""

    await ensure_translate_status_dicts(session, workspace_id=workspace_id)
    rows, total = await translate_repo.list_doc_translate_jobs_filtered(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        file_name=file_name,
        status=status,
        create_at_start=create_at_start,
        create_at_end=create_at_end,
    )
    return DocTranslateJobListOut(items=[_job_list_item(r) for r in rows], total=total)


@router.get("/jobs/{job_id}", response_model=DocTranslateJobDetailOut)
async def get_translate_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> DocTranslateJobDetailOut:
    """Return one job for polling progress."""

    row = await translate_repo.get_doc_translate_job(
        session, workspace_id=workspace_id, job_id=job_id
    )
    if row is None:
        raise AppError("translate.job_not_found", "翻译任务不存在。", 404)
    return DocTranslateJobDetailOut(
        id=row.id,
        title=row.title,
        file_name=row.file_name,
        file_ext=row.file_ext,
        source_lang=row.source_lang,
        target_lang=row.target_lang,
        source_object_key=row.source_object_key,
        result_object_key=row.result_object_key,
        segment_total=int(row.segment_total or 0),
        segment_done=int(row.segment_done or 0),
        status=row.status,
        progress=int(row.progress or 0),
        create_at=row.create_at,
        update_at=row.update_at,
        model_id=row.model_id,
        ocr_file_id=row.ocr_file_id,
        error_code=row.error_code,
        error_message=row.error_message,
    )


@router.get("/jobs/{job_id}/layout-pages", response_model=OcrLayoutPagesOut)
async def get_translate_job_layout_pages_endpoint(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrLayoutPagesOut:
    """Return per-page layout blocks and bilingual markdown for preview."""

    return await get_translate_job_layout_pages(
        session=session, workspace_id=workspace_id, job_id=job_id
    )


@router.get("/jobs/{job_id}/segments", response_model=DocTranslateSegmentListOut)
async def list_translate_job_segments(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    group_by: Literal["page", "label", "none"] = Query(default="page"),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> DocTranslateSegmentListOut:
    """Return paragraph pairs for side-by-side comparison."""

    job = await translate_repo.get_doc_translate_job(
        session, workspace_id=workspace_id, job_id=job_id
    )
    if job is None:
        raise AppError("translate.job_not_found", "翻译任务不存在。", 404)
    rows = await translate_repo.list_segments_by_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
        limit=DOC_TRANSLATE_SEGMENTS_MAX_RETURN,
    )
    segment_outs = [
        DocTranslateSegmentOut(
            id=s.id,
            seq=s.seq,
            source_text=s.source_text,
            translated_text=s.translated_text,
            status=s.status,
        )
        for s in rows
    ]
    groups: list[DocTranslateSegmentGroupOut] | None = None
    if group_by != "none":
        bucket: dict[tuple[int | None, str | None], list[DocTranslateSegmentOut]] = {}
        for out, row in zip(segment_outs, rows, strict=True):
            anchor = row.anchor_json if isinstance(row.anchor_json, dict) else {}
            label = anchor.get("label") if group_by == "label" else None
            if group_by == "page":
                key = (_segment_page_index(row), None)
            else:
                key = (None, str(label) if label else None)
            bucket.setdefault(key, []).append(out)
        groups = [
            DocTranslateSegmentGroupOut(
                page_index=k[0],
                label=k[1],
                segments=v,
            )
            for k, v in sorted(bucket.items(), key=lambda item: (item[0][0] is None, item[0][0] or 0, item[0][1] or ""))
        ]
    return DocTranslateSegmentListOut(segments=segment_outs, groups=groups)


@router.get("/jobs/{job_id}/download", response_model=None)
async def download_translate_result(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    """Redirect to a presigned URL for the translated file."""

    row = await translate_repo.get_doc_translate_job(
        session, workspace_id=workspace_id, job_id=job_id
    )
    if row is None:
        raise AppError("translate.job_not_found", "翻译任务不存在。", 404)
    if row.status != DOC_TRANSLATE_STATUS_SUCCESS or not row.result_object_key:
        raise AppError("translate.download_not_ready", "译文尚未就绪。", 409)
    s3 = S3FileService(session=session)
    redirect = await s3.get_download_redirect(
        workspace_id=workspace_id, object_key=row.result_object_key
    )
    return RedirectResponse(url=redirect.url, status_code=302)


@router.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_translate_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete job, segments, and S3 objects."""

    ok = await delete_doc_translate_job(session, workspace_id=workspace_id, job_id=job_id)
    if not ok:
        raise AppError("translate.job_not_found", "翻译任务不存在。", 404)
    await session.commit()
