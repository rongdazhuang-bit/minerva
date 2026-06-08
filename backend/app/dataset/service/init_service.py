"""Initialize knowledge bases and enqueue indexing jobs."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery_app
from app.config import settings
from app.dataset.domain.constants import (
    DATASET_INDEXING_TASK_NAME,
    DATA_SOURCE_UPLOAD_FILE,
    DEFAULT_PROCESS_RULE,
    DEFAULT_RETRIEVAL_MODEL,
    DOC_FORM_TEXT,
    INDEXING_STATUS_WAITING,
    INDEXING_TECHNIQUE_ECONOMY,
    INDEXING_TECHNIQUE_HIGH_QUALITY,
)
from app.dataset.domain.db.models import Dataset, DatasetDocument, DatasetProcessRule, DatasetUploadFile
from app.dataset.service.chunk_service import serialize_process_rule
from app.exceptions import AppError


def _validate_init_payload(
    *,
    indexing_technique: str,
    embedding_model: str | None,
    embedding_model_provider: str | None,
    file_ids: list[uuid.UUID],
) -> None:
    """Validate create-wizard payload before persistence."""

    if indexing_technique not in {INDEXING_TECHNIQUE_HIGH_QUALITY, INDEXING_TECHNIQUE_ECONOMY}:
        raise AppError("dataset.indexing_technique_invalid", "索引方式无效。", 422)
    if not file_ids:
        raise AppError("dataset.file_ids_required", "请至少上传一个文件。", 422)
    if len(file_ids) > settings.dataset_max_files_per_dataset:
        raise AppError("dataset.too_many_files", "文件数量超过知识库上限。", 422)
    if indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY and (
        not embedding_model or not embedding_model_provider
    ):
        raise AppError("dataset.embedding_required", "高质量模式需要选择 Embedding 模型。", 422)


def _enqueue_indexing(dataset_id: uuid.UUID, document_ids: list[uuid.UUID]) -> str | None:
    """Send Celery indexing task to the dataset queue."""

    if celery_app is None:
        return None
    result = celery_app.send_task(
        DATASET_INDEXING_TASK_NAME,
        args=[str(dataset_id), [str(doc_id) for doc_id in document_ids]],
        queue="dataset",
    )
    return str(result.id)


async def init_dataset_with_documents(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    name: str,
    description: str | None,
    indexing_technique: str,
    doc_form: str,
    file_ids: list[uuid.UUID],
    process_rule: dict[str, Any] | None,
    retrieval_model: dict[str, Any] | None,
    embedding_model: str | None,
    embedding_model_provider: str | None,
) -> dict[str, Any]:
    """Create dataset, process rule, documents, and enqueue indexing."""

    _validate_init_payload(
        indexing_technique=indexing_technique,
        embedding_model=embedding_model,
        embedding_model_provider=embedding_model_provider,
        file_ids=file_ids,
    )
    rule_payload = process_rule or DEFAULT_PROCESS_RULE
    retrieval_payload = retrieval_model or DEFAULT_RETRIEVAL_MODEL
    collection_name = None
    index_struct = None
    if indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:
        dataset_id = uuid.uuid4()
        collection_name = Dataset.gen_collection_name(dataset_id)
        index_struct = json.dumps(
            {"type": settings.dataset_vector_store, "vector_store": {"class_prefix": collection_name}}
        )
    else:
        dataset_id = uuid.uuid4()

    dataset = Dataset(
        id=dataset_id,
        workspace_id=workspace_id,
        name=name.strip(),
        description=description,
        data_source_type=DATA_SOURCE_UPLOAD_FILE,
        indexing_technique=indexing_technique,
        index_struct=index_struct,
        embedding_model=embedding_model,
        embedding_model_provider=embedding_model_provider,
        retrieval_model=retrieval_payload,
        chunk_structure=doc_form or DOC_FORM_TEXT,
        created_by=user_id,
        updated_by=user_id,
    )
    session.add(dataset)

    process_row = DatasetProcessRule(
        id=uuid.uuid4(),
        dataset_id=dataset.id,
        mode=str(rule_payload.get("mode") or "custom"),
        rules=serialize_process_rule(rule_payload),
        created_by=user_id,
    )
    session.add(process_row)

    batch = uuid.uuid4().hex
    documents: list[DatasetDocument] = []
    for position, upload_id in enumerate(file_ids, start=1):
        upload = await session.get(DatasetUploadFile, upload_id)
        if upload is None or upload.workspace_id != workspace_id:
            raise AppError("dataset.upload_not_found", "上传文件不存在或不属于当前工作区。", 404)
        doc = DatasetDocument(
            id=uuid.uuid4(),
            workspace_id=workspace_id,
            dataset_id=dataset.id,
            position=position,
            data_source_type=DATA_SOURCE_UPLOAD_FILE,
            data_source_info=json.dumps({"upload_file_id": str(upload_id)}),
            dataset_process_rule_id=process_row.id,
            batch=batch,
            name=upload.name,
            created_from="web",
            created_by=user_id,
            file_id=str(upload_id),
            indexing_status=INDEXING_STATUS_WAITING,
            doc_form=doc_form or DOC_FORM_TEXT,
        )
        session.add(doc)
        documents.append(doc)
    await session.flush()
    await session.commit()
    await session.refresh(dataset)
    for doc in documents:
        await session.refresh(doc)

    task_id = _enqueue_indexing(dataset.id, [doc.id for doc in documents])
    return {
        "dataset": {
            "id": dataset.id,
            "name": dataset.name,
            "description": dataset.description,
            "indexing_technique": dataset.indexing_technique,
            "collection_name": collection_name,
        },
        "batch": batch,
        "documents": [
            {
                "id": doc.id,
                "name": doc.name,
                "indexing_status": doc.indexing_status,
                "batch": doc.batch,
            }
            for doc in documents
        ],
        "indexing_task_id": task_id,
    }
