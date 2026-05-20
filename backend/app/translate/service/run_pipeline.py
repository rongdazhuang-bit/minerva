"""Celery worker pipeline: download, extract, translate segments, assemble, upload."""

from __future__ import annotations

import logging
import tempfile
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.exceptions import AppError
from app.s3.service.s3_file_service import S3FileService
from app.translate.domain.constants import (
    DOC_TRANSLATE_SEGMENT_DONE,
    DOC_TRANSLATE_SEGMENT_FAILED,
    DOC_TRANSLATE_SEGMENT_PENDING,
    DOC_TRANSLATE_STATUS_ASSEMBLING,
    DOC_TRANSLATE_STATUS_EXTRACTING,
    DOC_TRANSLATE_STATUS_FAILED,
    DOC_TRANSLATE_STATUS_OCR_RUNNING,
    DOC_TRANSLATE_STATUS_SUCCESS,
    DOC_TRANSLATE_STATUS_TRANSLATING,
)
from app.translate.domain.db.models import DocTranslateJob, DocTranslateSegment
from app.translate.domain.dto import SegmentDraft, SegmentRecord
from app.translate.infrastructure import repository as translate_repo
from app.translate.service.ocr_bridge import run_ocr_and_load_pages
from app.translate.service.strategies.registry import get_doc_translate_strategy
from app.translate.service.translate_llm import translate_segment

log = logging.getLogger(__name__)


async def _download_source_to_path(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    object_key: str,
    dest: Path,
) -> None:
    """Stream one S3 object into a local file."""

    s3 = S3FileService(session=session)
    proxy = await s3.get_download_proxy(workspace_id=workspace_id, object_key=object_key)
    dest.write_bytes(proxy.stream.read())


async def run_job_once(session: AsyncSession, job_id: uuid.UUID) -> dict[str, Any]:
    """Execute the full translation pipeline for one job id."""

    job = (
        await session.execute(select(DocTranslateJob).where(DocTranslateJob.id == job_id))
    ).scalar_one_or_none()
    if job is None:
        return {"ok": False, "reason": "job_not_found"}

    workspace_id = job.workspace_id
    try:
        with tempfile.TemporaryDirectory(prefix="doc_translate_") as tmp:
            tmp_dir = Path(tmp)
            src_path = tmp_dir / f"source.{job.file_ext}"
            out_path = tmp_dir / f"result.{job.file_ext}"

            await _download_source_to_path(
                session,
                workspace_id=workspace_id,
                object_key=job.source_object_key,
                dest=src_path,
            )

            strategy = get_doc_translate_strategy(job.file_ext)
            ocr_pages: list[tuple[int, str]] | None = None
            if strategy.needs_ocr(src_path):
                await translate_repo.update_doc_translate_job(
                    session,
                    job_id=job_id,
                    workspace_id=workspace_id,
                    status=DOC_TRANSLATE_STATUS_OCR_RUNNING,
                )
                await session.commit()
                _ocr_id, ocr_pages = await run_ocr_and_load_pages(
                    session,
                    workspace_id=workspace_id,
                    job_id=job_id,
                    source_object_key=job.source_object_key,
                    file_name=job.file_name or f"file.{job.file_ext}",
                    file_size=None,
                )

            await translate_repo.update_doc_translate_job(
                session,
                job_id=job_id,
                workspace_id=workspace_id,
                status=DOC_TRANSLATE_STATUS_EXTRACTING,
            )
            await session.commit()

            drafts: list[SegmentDraft] = strategy.extract(
                src_path,
                ocr_file_id=job.ocr_file_id,
                ocr_pages=ocr_pages,
            )
            if not drafts:
                raise AppError("translate.extract_failed", "未能抽取可翻译段落。", 422)

            await translate_repo.bulk_insert_segments(
                session,
                workspace_id=workspace_id,
                job_id=job_id,
                segments=[
                    {
                        "seq": d.seq,
                        "source_text": d.source_text,
                        "status": DOC_TRANSLATE_SEGMENT_PENDING,
                        "anchor_json": d.anchor_json,
                    }
                    for d in drafts
                ],
            )
            total = len(drafts)
            await translate_repo.update_doc_translate_job(
                session,
                job_id=job_id,
                workspace_id=workspace_id,
                status=DOC_TRANSLATE_STATUS_TRANSLATING,
                segment_total=total,
                segment_done=0,
                progress=0,
            )
            await session.commit()

            seg_rows = await translate_repo.list_segments_by_job(
                session,
                workspace_id=workspace_id,
                job_id=job_id,
                limit=10000,
            )
            done_count = 0
            for seg in seg_rows:
                try:
                    translated = await translate_segment(
                        session,
                        workspace_id=workspace_id,
                        model_id=job.model_id,
                        source_lang=job.source_lang,
                        target_lang=job.target_lang,
                        source_text=seg.source_text,
                    )
                    await translate_repo.update_segment_translation(
                        session,
                        segment_id=seg.id,
                        workspace_id=workspace_id,
                        translated_text=translated,
                        status=DOC_TRANSLATE_SEGMENT_DONE,
                    )
                except Exception as exc:
                    await translate_repo.update_segment_translation(
                        session,
                        segment_id=seg.id,
                        workspace_id=workspace_id,
                        translated_text=None,
                        status=DOC_TRANSLATE_SEGMENT_FAILED,
                        error_message=str(exc)[:500],
                    )
                    raise
                done_count += 1
                progress = int(done_count * 100 / total) if total else 100
                await translate_repo.update_doc_translate_job(
                    session,
                    job_id=job_id,
                    workspace_id=workspace_id,
                    segment_done=done_count,
                    progress=min(progress, 99),
                )
                await session.commit()

            await translate_repo.update_doc_translate_job(
                session,
                job_id=job_id,
                workspace_id=workspace_id,
                status=DOC_TRANSLATE_STATUS_ASSEMBLING,
                progress=99,
            )
            await session.commit()

            refreshed = await translate_repo.list_segments_by_job(
                session,
                workspace_id=workspace_id,
                job_id=job_id,
                limit=10000,
            )
            records = [
                SegmentRecord(
                    seq=s.seq,
                    source_text=s.source_text,
                    translated_text=s.translated_text or s.source_text,
                    anchor_json=s.anchor_json if isinstance(s.anchor_json, dict) else None,
                )
                for s in refreshed
            ]
            strategy.assemble(records, src_path, out_path)
            payload = out_path.read_bytes()
            s3 = S3FileService(session=session)
            upload = await s3.upload_file(
                workspace_id=workspace_id,
                module_prefix="translate/result",
                file_name=job.file_name or f"translated.{job.file_ext}",
                payload=payload,
                content_type=None,
            )
            await translate_repo.update_doc_translate_job(
                session,
                job_id=job_id,
                workspace_id=workspace_id,
                status=DOC_TRANSLATE_STATUS_SUCCESS,
                result_object_key=upload.object_key,
                progress=100,
                segment_done=total,
            )
            await session.commit()
            return {"ok": True, "job_id": str(job_id)}

    except Exception as exc:
        log.exception("doc_translate job failed job_id=%s", job_id)
        code = exc.code if isinstance(exc, AppError) else "translate.pipeline_failed"
        msg = exc.message if isinstance(exc, AppError) else str(exc)
        await translate_repo.update_doc_translate_job(
            session,
            job_id=job_id,
            workspace_id=workspace_id,
            status=DOC_TRANSLATE_STATUS_FAILED,
            error_code=str(code)[:64],
            error_message=str(msg)[:2000],
        )
        await session.commit()
        return {"ok": False, "job_id": str(job_id), "error": str(msg)}
