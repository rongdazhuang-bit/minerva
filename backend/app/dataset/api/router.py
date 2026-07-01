"""HTTP routes for workspace knowledge bases."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.dataset.api.deps import require_dataset_workspace
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.dataset.api.schemas import (
    DatasetBatchIndexingStatusOut,
    DatasetChildChunkCreateIn,
    DatasetChildChunkListOut,
    DatasetChildChunkOut,
    DatasetChildChunkPatchIn,
    DatasetCreateIn,
    DatasetDetailOut,
    DatasetDocumentAppendIn,
    DatasetDocumentAppendOut,
    DatasetDocumentIndexingStatusOut,
    DatasetDocumentPatchIn,
    DatasetRetryOut,
    DatasetDocumentListPageOut,
    DatasetDocumentOut,
    DatasetIndexingEstimateIn,
    DatasetIndexingEstimateOut,
    DatasetInitIn,
    DatasetInitOut,
    DatasetListItemOut,
    DatasetListPageOut,
    DatasetPatchIn,
    DatasetProcessRuleOut,
    DatasetSegmentCreateIn,
    DatasetSegmentListPageOut,
    DatasetSegmentOut,
    DatasetSegmentPatchIn,
    DatasetUploadOut,
    HitTestingIn,
    HitTestingOut,
    DatasetQueryListPageOut,
    DatasetQueryOut,
)
from app.dataset.domain.constants import DEFAULT_PROCESS_RULE
from app.dataset.infrastructure import repository as repo
from app.dataset.service import dataset_service as dataset_svc
from app.dataset.service import document_service as document_svc
from app.dataset.service import segment_service as segment_svc
from app.dataset.service.chunk_service import estimate_indexing
from app.dataset.service import hit_testing_service as hit_testing_svc
from app.dataset.service.init_service import init_dataset_with_documents
from app.dataset.service.upload_service import upload_dataset_file
from app.exceptions import AppError
from app.pagination import DEFAULT_PAGE_SIZE

router = APIRouter(prefix="/workspaces/{workspace_id}/datasets", tags=["datasets"])


@router.get("", response_model=DatasetListPageOut)
async def list_datasets(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    name: str | None = Query(default=None, description="知识库名称关键词"),
    indexing_technique: str | None = Query(default=None, description="high_quality 或 economy"),
    created_from: datetime | None = Query(default=None),
    created_to: datetime | None = Query(default=None),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetListPageOut:
    """List knowledge bases with optional name, indexing mode, and date filters."""

    items_raw, total = await dataset_svc.list_dataset_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        name=name,
        indexing_technique=indexing_technique,
        created_from=created_from,
        created_to=created_to,
    )
    items = [DatasetListItemOut.model_validate(row) for row in items_raw]
    return DatasetListPageOut(items=items, total=total)


@router.post("", response_model=DatasetDetailOut, status_code=201)
async def create_dataset(
    workspace_id: uuid.UUID,
    body: DatasetCreateIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDetailOut:
    """Create an empty knowledge base (Dify POST /datasets)."""

    payload = await dataset_svc.create_empty_dataset(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
    )
    return DatasetDetailOut.model_validate(payload)


@router.post("/files/upload", response_model=DatasetUploadOut)
async def upload_dataset_source_file(
    workspace_id: uuid.UUID,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetUploadOut:
    """Upload one source file for dataset ingestion."""

    row = await upload_dataset_file(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        file=file,
    )
    await session.commit()
    return DatasetUploadOut(
        id=row.id,
        name=row.name,
        size=row.size,
        extension=row.extension,
        mime_type=row.mime_type,
    )


@router.get("/process-rule", response_model=DatasetProcessRuleOut)
async def get_default_process_rule(
    workspace_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
) -> DatasetProcessRuleOut:
    """Return default chunking and cleaning rules."""

    return DatasetProcessRuleOut(process_rule=DEFAULT_PROCESS_RULE)


@router.post("/indexing-estimate", response_model=DatasetIndexingEstimateOut)
async def estimate_dataset_indexing(
    workspace_id: uuid.UUID,
    body: DatasetIndexingEstimateIn,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetIndexingEstimateOut:
    """Preview chunking for uploaded files without persisting a dataset."""

    result = await estimate_indexing(
        session,
        workspace_id=workspace_id,
        file_ids=body.file_ids,
        process_rule=body.process_rule or DEFAULT_PROCESS_RULE,
        preview_file_id=body.preview_file_id,
        doc_form=body.doc_form,
    )
    return DatasetIndexingEstimateOut.model_validate(result)


@router.post("/init", response_model=DatasetInitOut)
async def init_dataset(
    workspace_id: uuid.UUID,
    body: DatasetInitIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetInitOut:
    """Create a knowledge base with documents and enqueue indexing."""

    result = await init_dataset_with_documents(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
        indexing_technique=body.indexing_technique,
        doc_form=body.doc_form,
        file_ids=body.file_ids,
        process_rule=body.process_rule,
        retrieval_model=body.retrieval_model,
        embedding_model=body.embedding_model,
        embedding_model_provider=body.embedding_model_provider,
    )
    return DatasetInitOut.model_validate(result)


@router.get("/{dataset_id}", response_model=DatasetDetailOut)
async def get_dataset(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDetailOut:
    """Return one knowledge base detail."""

    payload = await dataset_svc.get_dataset_detail(
        session, workspace_id=workspace_id, dataset_id=dataset_id
    )
    return DatasetDetailOut.model_validate(payload)


@router.patch("/{dataset_id}", response_model=DatasetDetailOut)
async def patch_dataset(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    body: DatasetPatchIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDetailOut:
    """Update knowledge base settings."""

    await dataset_svc.update_dataset(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        user_id=user.id,
        patch=body.model_dump(exclude_unset=True),
    )
    payload = await dataset_svc.get_dataset_detail(
        session, workspace_id=workspace_id, dataset_id=dataset_id
    )
    return DatasetDetailOut.model_validate(payload)


@router.delete("/{dataset_id}", status_code=204)
async def delete_dataset(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete one knowledge base and all dependent rows."""

    await dataset_svc.delete_dataset(
        session, workspace_id=workspace_id, dataset_id=dataset_id
    )


@router.get("/{dataset_id}/documents", response_model=DatasetDocumentListPageOut)
async def list_documents(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    keyword: str | None = Query(default=None),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentListPageOut:
    """List documents within one knowledge base."""

    items, total = await document_svc.list_document_page(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
    )
    return DatasetDocumentListPageOut(
        items=[DatasetDocumentOut.model_validate(row) for row in items],
        total=total,
    )


@router.post("/{dataset_id}/documents", response_model=DatasetDocumentAppendOut)
async def append_documents(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    body: DatasetDocumentAppendIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentAppendOut:
    """Append uploaded files to an existing knowledge base."""

    result = await document_svc.append_documents(
        session,
        workspace_id=workspace_id,
        user_id=user.id,
        dataset_id=dataset_id,
        file_ids=body.file_ids,
        process_rule=body.process_rule,
    )
    return DatasetDocumentAppendOut.model_validate(result)


@router.get("/{dataset_id}/documents/{document_id}", response_model=DatasetDocumentOut)
async def get_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Return one document detail."""

    payload = await document_svc.get_document_detail(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.patch("/{dataset_id}/documents/{document_id}", response_model=DatasetDocumentOut)
async def patch_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DatasetDocumentPatchIn,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Rename or update one document."""

    payload = await document_svc.update_document(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        user_id=_member,
        patch=body.model_dump(exclude_unset=True),
    )
    return DatasetDocumentOut.model_validate(payload)


@router.get(
    "/{dataset_id}/documents/{document_id}/indexing-status",
    response_model=DatasetDocumentIndexingStatusOut,
)
async def get_document_indexing_status(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentIndexingStatusOut:
    """Return indexing progress for one document."""

    payload = await document_svc.get_document_indexing_status(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    return DatasetDocumentIndexingStatusOut.model_validate(payload)


@router.delete("/{dataset_id}/documents/{document_id}", status_code=204)
async def delete_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete one document."""

    await document_svc.delete_document(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )


@router.post("/{dataset_id}/documents/{document_id}/status/enable", response_model=DatasetDocumentOut)
async def enable_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Enable one document."""

    payload = await document_svc.set_document_enabled(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        enabled=True,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.post("/{dataset_id}/documents/{document_id}/status/disable", response_model=DatasetDocumentOut)
async def disable_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Disable one document."""

    payload = await document_svc.set_document_enabled(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        enabled=False,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.post("/{dataset_id}/documents/{document_id}/retry", response_model=DatasetDocumentOut)
async def retry_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Retry indexing for one failed document."""

    payload = await document_svc.retry_document(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.post(
    "/{dataset_id}/documents/{document_id}/reprocess",
    response_model=DatasetDocumentOut,
)
async def reprocess_document_indexing(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Reprocess one document with its current process_rule and enqueue indexing."""

    payload = await document_svc.reprocess_document_indexing(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.post("/{dataset_id}/retry", response_model=DatasetRetryOut)
async def retry_dataset(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetRetryOut:
    """Retry all failed documents in one knowledge base."""

    payload = await document_svc.retry_failed_documents(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
    )
    return DatasetRetryOut.model_validate(payload)


@router.post("/{dataset_id}/documents/{document_id}/processing/pause", response_model=DatasetDocumentOut)
async def pause_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Mark one document as paused."""

    payload = await document_svc.set_document_paused(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        paused=True,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.post("/{dataset_id}/documents/{document_id}/processing/resume", response_model=DatasetDocumentOut)
async def resume_document(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetDocumentOut:
    """Resume one paused document."""

    payload = await document_svc.set_document_paused(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        paused=False,
    )
    return DatasetDocumentOut.model_validate(payload)


@router.get(
    "/{dataset_id}/documents/{document_id}/segments",
    response_model=DatasetSegmentListPageOut,
)
async def list_segments(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    keyword: str | None = Query(default=None),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetSegmentListPageOut:
    """List segments for one document."""

    items, total = await segment_svc.list_segment_page(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        page=page,
        page_size=page_size,
        keyword=keyword,
    )
    return DatasetSegmentListPageOut(
        items=[DatasetSegmentOut.model_validate(row) for row in items],
        total=total,
    )


@router.post(
    "/{dataset_id}/documents/{document_id}/segment",
    response_model=DatasetSegmentOut,
)
async def create_segment(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    body: DatasetSegmentCreateIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetSegmentOut:
    """Create one segment and sync indexes."""

    payload = await segment_svc.create_segment(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        user_id=user.id,
        content=body.content,
    )
    return DatasetSegmentOut.model_validate(payload)


@router.patch(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}",
    response_model=DatasetSegmentOut,
)
async def patch_segment(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: DatasetSegmentPatchIn,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetSegmentOut:
    """Update segment content and rebuild indexes."""

    payload = await segment_svc.update_segment(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        content=body.content,
    )
    return DatasetSegmentOut.model_validate(payload)


@router.get(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}/child_chunks",
    response_model=DatasetChildChunkListOut,
)
async def list_segment_child_chunks(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetChildChunkListOut:
    """List child chunks for one parent segment (hierarchical mode)."""

    items = await segment_svc.list_child_chunks(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )
    return DatasetChildChunkListOut(items=items)


@router.post(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}/child_chunks",
    response_model=DatasetChildChunkOut,
    status_code=201,
)
async def create_segment_child_chunk(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    body: DatasetChildChunkCreateIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetChildChunkOut:
    """Create one child chunk under a parent segment (Dify POST child_chunks)."""

    payload = await segment_svc.create_child_chunk(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        user_id=user.id,
        content=body.content,
    )
    return DatasetChildChunkOut.model_validate(payload)


@router.patch(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}/child_chunks/{child_chunk_id}",
    response_model=DatasetChildChunkOut,
)
async def patch_segment_child_chunk(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    child_chunk_id: uuid.UUID,
    body: DatasetChildChunkPatchIn,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetChildChunkOut:
    """Update one child chunk content and rebuild its index."""

    payload = await segment_svc.update_child_chunk(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        child_chunk_id=child_chunk_id,
        content=body.content,
    )
    return DatasetChildChunkOut.model_validate(payload)


@router.delete(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}/child_chunks/{child_chunk_id}",
    status_code=204,
)
async def delete_segment_child_chunk(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    child_chunk_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete one child chunk and remove its vector/keyword index."""

    await segment_svc.delete_child_chunk(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        child_chunk_id=child_chunk_id,
    )


@router.delete(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}",
    status_code=204,
)
async def delete_segment(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> None:
    """Delete one segment."""

    await segment_svc.delete_segment(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
    )


@router.post(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}/enable",
    response_model=DatasetSegmentOut,
)
async def enable_segment(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetSegmentOut:
    """Enable one segment."""

    payload = await segment_svc.set_segment_enabled(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        enabled=True,
    )
    return DatasetSegmentOut.model_validate(payload)


@router.post(
    "/{dataset_id}/documents/{document_id}/segments/{segment_id}/disable",
    response_model=DatasetSegmentOut,
)
async def disable_segment(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    document_id: uuid.UUID,
    segment_id: uuid.UUID,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetSegmentOut:
    """Disable one segment."""

    payload = await segment_svc.set_segment_enabled(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        enabled=False,
    )
    return DatasetSegmentOut.model_validate(payload)


@router.post("/{dataset_id}/hit-testing", response_model=HitTestingOut)
async def hit_testing(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    body: HitTestingIn,
    user: User = Depends(get_current_user),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> HitTestingOut:
    """Run recall test against dataset segments."""

    payload = await hit_testing_svc.run_hit_testing(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        user_id=user.id,
        query=body.query,
        retrieval_model=body.retrieval_model,
    )
    return HitTestingOut.model_validate(payload)


@router.get("/{dataset_id}/queries", response_model=DatasetQueryListPageOut)
async def list_dataset_queries(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetQueryListPageOut:
    """List hit-testing query history."""

    items, total = await hit_testing_svc.list_query_history(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        page=page,
        page_size=page_size,
    )
    return DatasetQueryListPageOut(
        items=[DatasetQueryOut.model_validate(row) for row in items],
        total=total,
    )


@router.get("/{dataset_id}/batch/{batch}/indexing-status", response_model=DatasetBatchIndexingStatusOut)
async def get_batch_indexing_status(
    workspace_id: uuid.UUID,
    dataset_id: uuid.UUID,
    batch: str,
    _member: uuid.UUID = Depends(require_dataset_workspace),
    session: AsyncSession = Depends(get_db),
) -> DatasetBatchIndexingStatusOut:
    """Poll indexing progress for one wizard batch."""

    dataset = await repo.get_dataset_for_workspace(
        session, workspace_id=workspace_id, dataset_id=dataset_id
    )
    if dataset is None:
        raise AppError("dataset.not_found", "知识库不存在。", 404)
    rows = await repo.list_documents_by_batch(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        batch=batch,
    )
    completed = sum(1 for row in rows if row.indexing_status == "completed")
    failed = sum(1 for row in rows if row.indexing_status == "error")
    processing = len(rows) - completed - failed
    return DatasetBatchIndexingStatusOut(
        batch=batch,
        total=len(rows),
        completed=completed,
        failed=failed,
        processing=processing,
        documents=[
            {
                "id": row.id,
                "name": row.name,
                "indexing_status": row.indexing_status,
                "error": row.error,
                "completed_at": row.completed_at,
                "processing_started_at": row.processing_started_at,
            }
            for row in rows
        ],
    )
