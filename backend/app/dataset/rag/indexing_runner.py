"""Document indexing pipeline: extract, chunk, embed, and vector load."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import jieba.analyse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.log import get_logger
from app.dataset.domain.constants import (
    DEFAULT_KEYWORD_NUMBER,
    DOC_FORM_HIERARCHICAL,
    INDEXING_STATUS_CLEANING,
    INDEXING_STATUS_COMPLETED,
    INDEXING_STATUS_ERROR,
    INDEXING_STATUS_INDEXING,
    INDEXING_STATUS_PARSING,
    INDEXING_STATUS_SPLITTING,
    INDEXING_STATUS_WAITING,
    INDEXING_TECHNIQUE_ECONOMY,
    INDEXING_TECHNIQUE_HIGH_QUALITY,
)
from app.dataset.domain.db.models import (
    Dataset,
    DatasetChildChunk,
    DatasetDocument,
    DatasetDocumentSegment,
    DatasetKeywordTable,
)
from app.dataset.infrastructure.vector.base import VectorFactory, vector_type_for_dataset
from app.dataset.rag.models import RagDocument
from app.dataset.service.chunk_service import (
    build_file_index_units,
    load_document_process_rule,
)
from app.dataset.service.embedding_service import embed_texts
from app.exceptions import AppError

log = get_logger(__name__)


def _now() -> datetime:
    """Return current UTC timestamp."""

    return datetime.now(tz=UTC)


def _segment_keywords(content: str, *, top_k: int) -> list[str]:
    """Extract keyword tags for economy-mode segments."""

    return list(jieba.analyse.extract_tags(content, topK=top_k))


async def _merge_keyword_table(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    segment_keywords: list[tuple[str, str]],
) -> None:
    """Merge segment keywords into dataset inverted index."""

    stmt = select(DatasetKeywordTable).where(DatasetKeywordTable.dataset_id == dataset_id)
    row = await session.scalar(stmt)
    table: dict[str, list[str]] = {}
    if row is not None:
        try:
            table = json.loads(row.keyword_table)
        except json.JSONDecodeError:
            table = {}
        if not isinstance(table, dict):
            table = {}
    for keyword, node_id in segment_keywords:
        bucket = table.setdefault(keyword, [])
        if node_id not in bucket:
            bucket.append(node_id)
    payload = json.dumps(table, ensure_ascii=False)
    if row is None:
        session.add(
            DatasetKeywordTable(
                id=uuid.uuid4(),
                dataset_id=dataset_id,
                keyword_table=payload,
                data_source_type="database",
            )
        )
    else:
        row.keyword_table = payload


async def _set_document_status(
    session: AsyncSession,
    document: DatasetDocument,
    status: str,
    *,
    error: str | None = None,
) -> None:
    """Update indexing status and optional error message."""

    document.indexing_status = status
    if error is not None:
        document.error = error
    now = _now()
    if status == INDEXING_STATUS_PARSING and document.processing_started_at is None:
        document.processing_started_at = now
    if status == INDEXING_STATUS_CLEANING:
        document.parsing_completed_at = now
    if status == INDEXING_STATUS_SPLITTING:
        document.cleaning_completed_at = now
    if status == INDEXING_STATUS_INDEXING:
        document.splitting_completed_at = now
    if status == INDEXING_STATUS_COMPLETED:
        document.completed_at = now
    document.update_at = now
    await session.flush()


async def index_one_document(
    session: AsyncSession,
    *,
    dataset: Dataset,
    document: DatasetDocument,
) -> None:
    """Run full indexing for one waiting document."""

    started = _now()
    try:
        await _set_document_status(session, document, INDEXING_STATUS_PARSING)
        process_rule = await load_document_process_rule(session, document=document)
        info = json.loads(document.data_source_info or "{}")
        upload_id = uuid.UUID(str(info.get("upload_file_id")))
        doc_form = document.doc_form or dataset.chunk_structure or "text_model"
        _, units = await build_file_index_units(
            session,
            workspace_id=dataset.workspace_id,
            upload_id=upload_id,
            process_rule=process_rule,
            doc_form=doc_form,
        )
        await _set_document_status(session, document, INDEXING_STATUS_CLEANING)
        await _set_document_status(session, document, INDEXING_STATUS_SPLITTING)

        segment_rows: list[DatasetDocumentSegment] = []
        child_rows: list[DatasetChildChunk] = []
        keyword_pairs: list[tuple[str, str]] = []
        rag_docs: list[RagDocument] = []
        for position, unit in enumerate(units, start=1):
            content = unit.content.strip()
            if not content:
                continue
            segment_id = uuid.uuid4()
            segment_row = DatasetDocumentSegment(
                id=segment_id,
                workspace_id=dataset.workspace_id,
                dataset_id=dataset.id,
                document_id=document.id,
                position=position,
                content=content,
                answer=unit.answer,
                word_count=len(content),
                tokens=max(1, len(content) // 4),
                keywords=None,
                index_node_id=None,
                index_node_hash=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                enabled=True,
                status=INDEXING_STATUS_WAITING,
                created_by=document.created_by,
            )
            segment_rows.append(segment_row)

            index_targets: list[tuple[str, str | None]] = []
            if doc_form == DOC_FORM_HIERARCHICAL and unit.children:
                for child_pos, child_text in enumerate(unit.children, start=1):
                    child_text = child_text.strip()
                    if not child_text:
                        continue
                    child_node_id = str(uuid.uuid4())
                    child_hash = hashlib.sha256(child_text.encode("utf-8")).hexdigest()
                    child_rows.append(
                        DatasetChildChunk(
                            id=uuid.uuid4(),
                            workspace_id=dataset.workspace_id,
                            dataset_id=dataset.id,
                            document_id=document.id,
                            segment_id=segment_id,
                            position=child_pos,
                            content=child_text,
                            word_count=len(child_text),
                            index_node_id=child_node_id,
                            index_node_hash=child_hash,
                            type="automatic",
                            created_by=document.created_by,
                        )
                    )
                    index_targets.append((child_text, child_node_id))
            else:
                node_id = str(uuid.uuid4())
                segment_row.index_node_id = node_id
                embed_text = content
                index_targets.append((embed_text, node_id))

            for embed_text, node_id in index_targets:
                if node_id is None:
                    continue
                keywords = _segment_keywords(
                    embed_text,
                    top_k=dataset.keyword_number or DEFAULT_KEYWORD_NUMBER,
                )
                if not segment_row.keywords:
                    segment_row.keywords = {"keywords": keywords}
                for kw in keywords:
                    keyword_pairs.append((kw, node_id))
                rag_docs.append(
                    RagDocument(
                        page_content=embed_text,
                        metadata={
                            "doc_id": node_id,
                            "document_id": str(document.id),
                            "dataset_id": str(dataset.id),
                            "segment_id": str(segment_id),
                            "doc_hash": hashlib.sha256(embed_text.encode("utf-8")).hexdigest(),
                        },
                    )
                )

        for row in segment_rows:
            session.add(row)
        for row in child_rows:
            session.add(row)
        document.word_count = sum(r.word_count for r in segment_rows)
        document.tokens = sum(r.tokens for r in segment_rows)
        await session.flush()

        if dataset.indexing_technique == INDEXING_TECHNIQUE_ECONOMY:
            await _merge_keyword_table(
                session,
                dataset_id=dataset.id,
                segment_keywords=keyword_pairs,
            )
            for row in segment_rows:
                row.status = INDEXING_STATUS_COMPLETED
        elif dataset.indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:
            if not dataset.embedding_model or not dataset.embedding_model_provider:
                raise AppError("dataset.embedding_required", "高质量模式需要配置 Embedding 模型。", 422)
            await _set_document_status(session, document, INDEXING_STATUS_INDEXING)
            texts = [doc.page_content for doc in rag_docs]
            vectors = await embed_texts(
                session,
                workspace_id=dataset.workspace_id,
                provider_name=dataset.embedding_model_provider,
                model_name=dataset.embedding_model,
                texts=texts,
            )
            collection = Dataset.gen_collection_name(dataset.id)
            vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))
            vector.create(rag_docs, vectors)
            for row in segment_rows:
                row.status = INDEXING_STATUS_COMPLETED
        else:
            raise AppError("dataset.indexing_technique_invalid", "不支持的索引方式。", 422)

        await _set_document_status(session, document, INDEXING_STATUS_COMPLETED)
        document.indexing_latency = (_now() - started).total_seconds()
        document.error = None
        await session.commit()
    except Exception as exc:
        await session.rollback()
        fresh_doc = await session.get(DatasetDocument, document.id)
        if fresh_doc is not None:
            fresh_doc.indexing_status = INDEXING_STATUS_ERROR
            fresh_doc.error = str(exc)[:2000]
            fresh_doc.indexing_latency = (_now() - started).total_seconds()
            fresh_doc.update_at = _now()
            await session.commit()
        log.exception(
            "dataset indexing failed dataset_id={} document_id={}",
            dataset.id,
            document.id,
        )
        raise


async def run_documents_indexing(
    session: AsyncSession,
    *,
    dataset_id: uuid.UUID,
    document_ids: list[uuid.UUID],
) -> dict[str, Any]:
    """Index multiple documents sequentially."""

    dataset = await session.get(Dataset, dataset_id)
    if dataset is None:
        return {"ok": False, "reason": "dataset_not_found"}
    processed = 0
    errors: list[str] = []
    for doc_id in document_ids:
        document = await session.get(DatasetDocument, doc_id)
        if document is None or document.dataset_id != dataset_id:
            errors.append(str(doc_id))
            continue
        try:
            await index_one_document(session, dataset=dataset, document=document)
            processed += 1
        except Exception:
            errors.append(str(doc_id))
    return {"ok": len(errors) == 0, "processed": processed, "errors": errors}
