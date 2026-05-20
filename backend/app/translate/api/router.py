"""Workspace HTTP routes for document translation."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.exceptions import AppError
from app.s3.service.s3_file_service import S3FileService
from app.translate.api.schemas import (
    DocTranslateJobCreateOut,
    DocTranslateJobDetailOut,
    DocTranslateJobListItemOut,
    DocTranslateJobListOut,
    DocTranslateSegmentListOut,
    DocTranslateSegmentOut,
)
from app.translate.domain.constants import (
    DOC_TRANSLATE_LIST_DEFAULT_LIMIT,
    DOC_TRANSLATE_LIST_MAX_LIMIT,
    DOC_TRANSLATE_SEGMENTS_MAX_RETURN,
    DOC_TRANSLATE_STATUS_SUCCESS,
)
from app.translate.infrastructure import repository as translate_repo
from app.translate.service.job_delete import delete_doc_translate_job
from app.translate.service.job_service import create_job_from_upload

router = APIRouter(prefix="/workspaces/{workspace_id}/translate", tags=["translate"])


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
    return DocTranslateJobCreateOut(id=job_id, status="PENDING")


@router.get("/jobs", response_model=DocTranslateJobListOut)
async def list_translate_jobs(
    workspace_id: uuid.UUID,
    limit: int = Query(default=DOC_TRANSLATE_LIST_DEFAULT_LIMIT, ge=1, le=DOC_TRANSLATE_LIST_MAX_LIMIT),
    cursor: str | None = Query(default=None),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> DocTranslateJobListOut:
    """List translation history for the sidebar."""

    cursor_update_at = None
    cursor_id = None
    if cursor:
        try:
            cursor_update_at, cursor_id = translate_repo.decode_doc_translate_job_cursor(cursor)
        except ValueError as e:
            raise AppError("translate.invalid_cursor", "任务列表游标无效。") from e

    rows, has_more = await translate_repo.list_doc_translate_jobs_recent(
        session,
        workspace_id=workspace_id,
        limit=limit,
        cursor_update_at=cursor_update_at,
        cursor_id=cursor_id,
    )
    next_cursor: str | None = None
    if has_more and rows:
        last = rows[-1]
        ts = last.update_at or last.create_at
        if ts is not None:
            next_cursor = translate_repo.encode_doc_translate_job_cursor(ts, last.id)
    return DocTranslateJobListOut(
        jobs=[
            DocTranslateJobListItemOut(
                id=r.id,
                title=r.title,
                file_name=r.file_name,
                file_ext=r.file_ext,
                source_lang=r.source_lang,
                target_lang=r.target_lang,
                status=r.status,
                progress=int(r.progress or 0),
                segment_total=int(r.segment_total or 0),
                segment_done=int(r.segment_done or 0),
                create_at=r.create_at,
                update_at=r.update_at,
            )
            for r in rows
        ],
        next_cursor=next_cursor,
    )


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
        status=row.status,
        progress=int(row.progress or 0),
        segment_total=int(row.segment_total or 0),
        segment_done=int(row.segment_done or 0),
        create_at=row.create_at,
        update_at=row.update_at,
        model_id=row.model_id,
        source_object_key=row.source_object_key,
        result_object_key=row.result_object_key,
        ocr_file_id=row.ocr_file_id,
        error_code=row.error_code,
        error_message=row.error_message,
    )


@router.get("/jobs/{job_id}/segments", response_model=DocTranslateSegmentListOut)
async def list_translate_job_segments(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
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
    return DocTranslateSegmentListOut(
        segments=[
            DocTranslateSegmentOut(
                id=s.id,
                seq=s.seq,
                source_text=s.source_text,
                translated_text=s.translated_text,
                status=s.status,
            )
            for s in rows
        ]
    )


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
