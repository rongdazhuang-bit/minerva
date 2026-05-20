"""Delete translation jobs and related S3 objects in application layer."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.s3.service.s3_file_service import S3FileService
from app.translate.infrastructure import repository as translate_repo


async def delete_doc_translate_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> bool:
    """Remove segments, S3 keys, and the job row."""

    row = await translate_repo.get_doc_translate_job(
        session, workspace_id=workspace_id, job_id=job_id
    )
    if row is None:
        return False
    s3 = S3FileService(session=session)
    try:
        await s3.delete_file(workspace_id=workspace_id, object_key=row.source_object_key)
    except Exception:
        pass
    if row.result_object_key:
        try:
            await s3.delete_file(workspace_id=workspace_id, object_key=row.result_object_key)
        except Exception:
            pass
    return await translate_repo.delete_doc_translate_job_dependents(
        session, workspace_id=workspace_id, job_id=job_id
    )
