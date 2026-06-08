"""Sync segment rows with vector and keyword indexes."""



from __future__ import annotations



import hashlib

import json

import uuid

from typing import Any



import jieba.analyse

from sqlalchemy import delete, select

from sqlalchemy.ext.asyncio import AsyncSession



from app.dataset.domain.constants import (

    DEFAULT_KEYWORD_NUMBER,

    DOC_FORM_HIERARCHICAL,

    INDEXING_STATUS_COMPLETED,

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

from app.dataset.infrastructure import repository as repo

from app.dataset.infrastructure.vector.base import VectorFactory, vector_type_for_dataset

from app.dataset.rag.index_processor import split_children_for_parent

from app.dataset.rag.models import RagDocument

from app.dataset.service.chunk_service import load_document_process_rule

from app.dataset.service.embedding_service import embed_texts

from app.exceptions import AppError





def extract_keywords(content: str, *, top_k: int) -> list[str]:

    """Extract keyword tags for economy-mode segments."""



    return list(jieba.analyse.extract_tags(content, topK=top_k))





async def _load_keyword_table(session: AsyncSession, dataset_id: uuid.UUID) -> dict[str, list[str]]:

    """Load inverted keyword index for a dataset."""



    row = await session.scalar(

        select(DatasetKeywordTable).where(DatasetKeywordTable.dataset_id == dataset_id)

    )

    if row is None:

        return {}

    try:

        table = json.loads(row.keyword_table)

    except json.JSONDecodeError:

        return {}

    return table if isinstance(table, dict) else {}





async def _save_keyword_table(

    session: AsyncSession,

    *,

    dataset_id: uuid.UUID,

    table: dict[str, list[str]],

) -> None:

    """Persist inverted keyword index."""



    payload = json.dumps(table, ensure_ascii=False)

    row = await session.scalar(

        select(DatasetKeywordTable).where(DatasetKeywordTable.dataset_id == dataset_id)

    )

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





async def add_segment_keywords(

    session: AsyncSession,

    *,

    dataset: Dataset,

    node_id: str,

    content: str,

) -> None:

    """Insert one segment node into the keyword table."""



    if dataset.indexing_technique != INDEXING_TECHNIQUE_ECONOMY:

        return

    table = await _load_keyword_table(session, dataset.id)

    top_k = dataset.keyword_number or DEFAULT_KEYWORD_NUMBER

    for keyword in extract_keywords(content, top_k=top_k):

        bucket = table.setdefault(keyword, [])

        if node_id not in bucket:

            bucket.append(node_id)

    await _save_keyword_table(session, dataset_id=dataset.id, table=table)





async def remove_segment_keywords(

    session: AsyncSession,

    *,

    dataset: Dataset,

    node_id: str,

) -> None:

    """Remove one segment node from the keyword table."""



    if dataset.indexing_technique != INDEXING_TECHNIQUE_ECONOMY:

        return

    table = await _load_keyword_table(session, dataset.id)

    changed = False

    for keyword, node_ids in list(table.items()):

        if node_id in node_ids:

            table[keyword] = [nid for nid in node_ids if nid != node_id]

            changed = True

        if not table[keyword]:

            del table[keyword]

    if changed:

        await _save_keyword_table(session, dataset_id=dataset.id, table=table)





async def remove_vector_node(

    session: AsyncSession,

    *,

    dataset: Dataset,

    node_id: str,

) -> None:

    """Remove one vector node by ``doc_id`` metadata."""



    _ = session

    if dataset.indexing_technique != INDEXING_TECHNIQUE_HIGH_QUALITY:

        return

    if not node_id:

        return

    collection = Dataset.gen_collection_name(dataset.id)

    vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))

    vector.delete_by_metadata_field("doc_id", node_id)





async def index_segment_vector(

    session: AsyncSession,

    *,

    dataset: Dataset,

    segment: DatasetDocumentSegment,

    document_id: uuid.UUID,

) -> None:

    """Embed and store one segment in the vector index."""



    if dataset.indexing_technique != INDEXING_TECHNIQUE_HIGH_QUALITY:

        return

    if not dataset.embedding_model or not dataset.embedding_model_provider:

        raise AppError("dataset.embedding_required", "高质量模式需要配置 Embedding 模型。", 422)

    node_id = segment.index_node_id or str(uuid.uuid4())

    segment.index_node_id = node_id

    segment.index_node_hash = hashlib.sha256(segment.content.encode("utf-8")).hexdigest()

    vectors = await embed_texts(

        session,

        workspace_id=dataset.workspace_id,

        provider_name=dataset.embedding_model_provider,

        model_name=dataset.embedding_model,

        texts=[segment.content],

    )

    rag_doc = RagDocument(

        page_content=segment.content,

        metadata={

            "doc_id": node_id,

            "document_id": str(document_id),

            "dataset_id": str(dataset.id),

            "segment_id": str(segment.id),

            "doc_hash": segment.index_node_hash,

        },

    )

    collection = Dataset.gen_collection_name(dataset.id)

    vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))

    vector.add_texts([rag_doc], vectors)





async def remove_segment_vector(

    session: AsyncSession,

    *,

    dataset: Dataset,

    segment: DatasetDocumentSegment,

) -> None:

    """Remove one segment vector node."""



    if not segment.index_node_id:

        return

    await remove_vector_node(session, dataset=dataset, node_id=segment.index_node_id)





async def _remove_child_chunk_indexes(

    session: AsyncSession,

    *,

    dataset: Dataset,

    child_rows: list[DatasetChildChunk],

) -> None:

    """Remove keyword and vector entries for child chunks."""



    for child in child_rows:

        if not child.index_node_id:

            continue

        await remove_segment_keywords(session, dataset=dataset, node_id=child.index_node_id)

        await remove_vector_node(session, dataset=dataset, node_id=child.index_node_id)





async def delete_child_chunks_for_segment(

    session: AsyncSession,

    *,

    dataset: Dataset,

    dataset_id: uuid.UUID,

    document_id: uuid.UUID,

    segment_id: uuid.UUID,

) -> None:

    """Remove child chunk indexes and rows for one parent segment."""



    child_rows = await repo.list_child_chunks_for_segment(

        session,

        dataset_id=dataset_id,

        document_id=document_id,

        segment_id=segment_id,

    )

    if not child_rows:

        return

    await _remove_child_chunk_indexes(session, dataset=dataset, child_rows=child_rows)

    await session.execute(

        delete(DatasetChildChunk).where(

            DatasetChildChunk.dataset_id == dataset_id,

            DatasetChildChunk.document_id == document_id,

            DatasetChildChunk.segment_id == segment_id,

        )

    )





async def _index_child_chunks(

    session: AsyncSession,

    *,

    dataset: Dataset,

    document: DatasetDocument,

    segment: DatasetDocumentSegment,

    child_texts: list[str],

    user_id: uuid.UUID,

) -> list[DatasetChildChunk]:

    """Persist child chunks and sync economy/vector indexes."""



    child_rows: list[DatasetChildChunk] = []

    rag_docs: list[RagDocument] = []

    for position, child_text in enumerate(child_texts, start=1):

        child_text = child_text.strip()

        if not child_text:

            continue

        child_node_id = str(uuid.uuid4())

        child_hash = hashlib.sha256(child_text.encode("utf-8")).hexdigest()

        child_row = DatasetChildChunk(

            id=uuid.uuid4(),

            workspace_id=dataset.workspace_id,

            dataset_id=dataset.id,

            document_id=document.id,

            segment_id=segment.id,

            position=position,

            content=child_text,

            word_count=len(child_text),

            index_node_id=child_node_id,

            index_node_hash=child_hash,

            type="manual",

            created_by=user_id,

        )

        child_rows.append(child_row)

        rag_docs.append(

            RagDocument(

                page_content=child_text,

                metadata={

                    "doc_id": child_node_id,

                    "document_id": str(document.id),

                    "dataset_id": str(dataset.id),

                    "segment_id": str(segment.id),

                    "doc_hash": child_hash,

                },

            )

        )



    for row in child_rows:

        session.add(row)

    await session.flush()



    if dataset.indexing_technique == INDEXING_TECHNIQUE_ECONOMY:

        for child in child_rows:

            await add_segment_keywords(

                session,

                dataset=dataset,

                node_id=child.index_node_id or "",

                content=child.content,

            )

    elif dataset.indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:

        if not dataset.embedding_model or not dataset.embedding_model_provider:

            raise AppError("dataset.embedding_required", "高质量模式需要配置 Embedding 模型。", 422)

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

        vector.add_texts(rag_docs, vectors)



    return child_rows


async def sync_child_chunk_index(
    session: AsyncSession,
    *,
    dataset: Dataset,
    document: DatasetDocument,
    segment: DatasetDocumentSegment,
    child: DatasetChildChunk,
) -> None:
    """Embed or keyword-index one child chunk (Dify customized child)."""

    if not child.index_node_id:
        child.index_node_id = str(uuid.uuid4())
    child.index_node_hash = hashlib.sha256(child.content.encode("utf-8")).hexdigest()
    rag_doc = RagDocument(
        page_content=child.content,
        metadata={
            "doc_id": child.index_node_id,
            "document_id": str(document.id),
            "dataset_id": str(dataset.id),
            "segment_id": str(segment.id),
            "doc_hash": child.index_node_hash,
        },
    )
    if dataset.indexing_technique == INDEXING_TECHNIQUE_ECONOMY:
        await add_segment_keywords(
            session,
            dataset=dataset,
            node_id=child.index_node_id,
            content=child.content,
        )
    elif dataset.indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:
        if not dataset.embedding_model or not dataset.embedding_model_provider:
            raise AppError("dataset.embedding_required", "高质量模式需要配置 Embedding 模型。", 422)
        vectors = await embed_texts(
            session,
            workspace_id=dataset.workspace_id,
            provider_name=dataset.embedding_model_provider,
            model_name=dataset.embedding_model,
            texts=[child.content],
        )
        collection = Dataset.gen_collection_name(dataset.id)
        vector = VectorFactory.build(collection, vector_type=vector_type_for_dataset(dataset))
        vector.add_texts([rag_doc], vectors)


async def remove_child_chunk_index(
    session: AsyncSession,
    *,
    dataset: Dataset,
    child: DatasetChildChunk,
) -> None:
    """Remove vector/keyword entries for one child chunk."""

    if not child.index_node_id:
        return
    await remove_segment_keywords(session, dataset=dataset, node_id=child.index_node_id)
    await remove_vector_node(session, dataset=dataset, node_id=child.index_node_id)


async def reindex_hierarchical_segment(

    session: AsyncSession,

    *,

    dataset: Dataset,

    document: DatasetDocument,

    segment: DatasetDocumentSegment,

    user_id: uuid.UUID,

    process_rule: dict[str, Any] | None,

) -> int:

    """Rebuild child chunks and indexes for one parent segment."""



    if segment.index_node_id:

        await remove_segment_keywords(session, dataset=dataset, node_id=segment.index_node_id)

        await remove_vector_node(session, dataset=dataset, node_id=segment.index_node_id)

        segment.index_node_id = None

        segment.index_node_hash = hashlib.sha256(segment.content.encode("utf-8")).hexdigest()



    await delete_child_chunks_for_segment(

        session,

        dataset=dataset,

        dataset_id=dataset.id,

        document_id=document.id,

        segment_id=segment.id,

    )

    child_texts = split_children_for_parent(segment.content, process_rule=process_rule)

    child_rows = await _index_child_chunks(

        session,

        dataset=dataset,

        document=document,

        segment=segment,

        child_texts=child_texts,

        user_id=user_id,

    )

    segment.status = INDEXING_STATUS_COMPLETED

    return len(child_rows)





async def reindex_segment(

    session: AsyncSession,

    *,

    dataset: Dataset,

    segment: DatasetDocumentSegment,

    document_id: uuid.UUID,

) -> None:

    """Rebuild keyword/vector indexes for one flat segment."""



    if segment.index_node_id:

        await remove_segment_keywords(session, dataset=dataset, node_id=segment.index_node_id)

        await remove_segment_vector(session, dataset=dataset, segment=segment)

    if not segment.index_node_id:

        segment.index_node_id = str(uuid.uuid4())

    if dataset.indexing_technique == INDEXING_TECHNIQUE_ECONOMY:

        await add_segment_keywords(

            session,

            dataset=dataset,

            node_id=segment.index_node_id,

            content=segment.content,

        )

    elif dataset.indexing_technique == INDEXING_TECHNIQUE_HIGH_QUALITY:

        await index_segment_vector(

            session,

            dataset=dataset,

            segment=segment,

            document_id=document_id,

        )

    segment.status = INDEXING_STATUS_COMPLETED





async def sync_segment_indexes(

    session: AsyncSession,

    *,

    dataset: Dataset,

    document: DatasetDocument,

    segment: DatasetDocumentSegment,

    user_id: uuid.UUID,

) -> int:

    """Rebuild indexes according to document chunk structure."""



    doc_form = (document.doc_form or dataset.chunk_structure or "text_model").strip()

    if doc_form == DOC_FORM_HIERARCHICAL:

        process_rule = await load_document_process_rule(session, document=document)

        return await reindex_hierarchical_segment(

            session,

            dataset=dataset,

            document=document,

            segment=segment,

            user_id=user_id,

            process_rule=process_rule,

        )

    await reindex_segment(

        session,

        dataset=dataset,

        segment=segment,

        document_id=document.id,

    )

    return 0





async def remove_segment_indexes(

    session: AsyncSession,

    *,

    dataset: Dataset,

    document: DatasetDocument,

    segment: DatasetDocumentSegment,

) -> None:

    """Remove flat or hierarchical indexes before deleting a segment."""



    doc_form = (document.doc_form or dataset.chunk_structure or "text_model").strip()

    if doc_form == DOC_FORM_HIERARCHICAL:

        await delete_child_chunks_for_segment(

            session,

            dataset=dataset,

            dataset_id=dataset.id,

            document_id=document.id,

            segment_id=segment.id,

        )

        if segment.index_node_id:

            await remove_segment_keywords(session, dataset=dataset, node_id=segment.index_node_id)

            await remove_vector_node(session, dataset=dataset, node_id=segment.index_node_id)

        return

    if segment.index_node_id:

        await remove_segment_keywords(session, dataset=dataset, node_id=segment.index_node_id)

        await remove_segment_vector(session, dataset=dataset, segment=segment)


