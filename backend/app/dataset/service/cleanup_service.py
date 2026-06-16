"""Async cleanup of external resources after dataset SQL delete."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log import get_logger
from app.dataset.domain.constants import INDEXING_TECHNIQUE_HIGH_QUALITY
from app.dataset.domain.db.models import DatasetUploadFile
from app.dataset.service.deletion_service import (
    DatasetCleanupManifest,
    delete_vector_collection,
    upload_referenced_by_other_dataset,
)
from app.s3.service.s3_file_service import S3FileService

log = get_logger(__name__)


async def run_dataset_cleanup(
    session: AsyncSession,
    manifest: DatasetCleanupManifest | dict[str, Any],
) -> dict[str, int]:
    """Best-effort delete S3 objects, upload rows, and vector collection."""

    workspace_id = uuid.UUID(str(manifest["workspace_id"]))
    dataset_id = uuid.UUID(str(manifest["dataset_id"]))
    indexing_technique = manifest.get("indexing_technique")
    summary = {"s3_deleted": 0, "s3_failed": 0, "upload_rows_deleted": 0, "vector_dropped": 0}

    s3 = S3FileService(session=session)
    for item in manifest.get("uploads") or []:
        upload_id = uuid.UUID(str(item["id"]))
        storage_key = str(item["storage_key"])
        if await upload_referenced_by_other_dataset(
            session,
            workspace_id=workspace_id,
            upload_id=upload_id,
            exclude_dataset_id=dataset_id,
        ):
            continue
        try:
            await s3.delete_file(workspace_id=workspace_id, object_key=storage_key)
            summary["s3_deleted"] += 1
        except Exception:
            log.exception(
                "dataset.cleanup s3_failed dataset_id={} upload_id={} storage_key={}",
                dataset_id,
                upload_id,
                storage_key,
            )
            summary["s3_failed"] += 1
        try:
            await session.execute(delete(DatasetUploadFile).where(DatasetUploadFile.id == upload_id))
            await session.commit()
            summary["upload_rows_deleted"] += 1
        except Exception:
            log.exception("dataset.cleanup upload_row_failed upload_id={}", upload_id)
            await session.rollback()

    if indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:
        try:
            from types import SimpleNamespace

            dataset_stub = SimpleNamespace(id=dataset_id, indexing_technique=indexing_technique)
            await delete_vector_collection(dataset_stub)  # type: ignore[arg-type]
            summary["vector_dropped"] = 1
        except Exception:
            log.exception("dataset.cleanup vector_failed dataset_id={}", dataset_id)

    return summary
