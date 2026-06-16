"""Chunk preview and segmentation helpers for dataset ingestion."""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.dataset.rag.clean import clean_text
from app.dataset.rag.extract import extract_text_from_bytes
from app.dataset.rag.index_processor import build_index_units
from app.dataset.rag.segmentation_rules import parse_segmentation
from app.dataset.service.file_loader import load_upload_bytes
from app.exceptions import AppError


async def build_file_segments(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    upload_id: uuid.UUID,
    process_rule: dict[str, Any] | None,
    doc_form: str = "text_model",
) -> tuple[str, list[str]]:
    """Extract, clean, and split one upload into segment texts."""

    upload, payload = await load_upload_bytes(
        session, workspace_id=workspace_id, upload_id=upload_id
    )
    raw = extract_text_from_bytes(payload, file_name=upload.name)
    cleaned = clean_text(raw, process_rule)
    units = build_index_units(cleaned, doc_form=doc_form, process_rule=process_rule)
    segments = [unit.content for unit in units if unit.content.strip()]
    return upload.name, segments


async def build_file_index_units(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    upload_id: uuid.UUID,
    process_rule: dict[str, Any] | None,
    doc_form: str = "text_model",
):
    """Extract, clean, and return structured index units for one upload."""

    upload, payload = await load_upload_bytes(
        session, workspace_id=workspace_id, upload_id=upload_id
    )
    raw = extract_text_from_bytes(payload, file_name=upload.name)
    cleaned = clean_text(raw, process_rule)
    units = build_index_units(cleaned, doc_form=doc_form, process_rule=process_rule)
    return upload.name, units


async def estimate_indexing(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    file_ids: list[uuid.UUID],
    process_rule: dict[str, Any] | None,
    preview_file_id: uuid.UUID | None = None,
    doc_form: str | None = None,
) -> dict[str, Any]:
    """Return segment previews without persisting dataset rows."""

    if not file_ids:
        raise AppError("dataset.file_ids_required", "请至少选择一个已上传文件。", 422)
    if len(file_ids) > settings.dataset_batch_upload_limit:
        raise AppError("dataset.too_many_files", "单次上传文件数量超过限制。", 422)

    target_ids = [preview_file_id] if preview_file_id else file_ids
    if preview_file_id and preview_file_id not in file_ids:
        raise AppError("dataset.preview_file_invalid", "预览文件不在已选列表中。", 422)

    previews: list[dict[str, Any]] = []
    total_segments = 0
    total_chars = 0
    for upload_id in target_ids:
        file_name, units = await build_file_index_units(
            session,
            workspace_id=workspace_id,
            upload_id=upload_id,
            process_rule=process_rule,
            doc_form=doc_form or "text_model",
        )
        segment_payloads = []
        for unit in units:
            item = {"content": unit.content, "word_count": len(unit.content)}
            if unit.answer:
                item["answer"] = unit.answer
            if unit.children:
                item["child_count"] = len(unit.children)
            segment_payloads.append(item)
        total_segments += len(units)
        total_chars += sum(len(unit.content) for unit in units)
        previews.append(
            {
                "file_id": str(upload_id),
                "file_name": file_name,
                "segment_count": len(units),
                "segments": segment_payloads[:20],
            }
        )
    return {
        "total_segments": total_segments,
        "total_chars": total_chars,
        "preview_file_count": len(target_ids),
        "previews": previews,
    }


def serialize_process_rule(process_rule: dict[str, Any]) -> str:
    """Persist process rule JSON as text."""

    return json.dumps(process_rule, ensure_ascii=False)


def deserialize_process_rule(raw: str | None) -> dict[str, Any]:
    """Load process rule JSON from DB text."""

    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


async def load_document_process_rule_for_detail(
    session: AsyncSession,
    *,
    document,
) -> dict[str, Any] | None:
    """Return persisted process rule for document detail API, or None when missing."""

    from app.dataset.domain.db.models import DatasetProcessRule

    if document.dataset_process_rule_id is None:
        return None
    row = await session.get(DatasetProcessRule, document.dataset_process_rule_id)
    if row is None:
        return None
    loaded = deserialize_process_rule(row.rules)
    return loaded if loaded else None


async def load_document_process_rule(
    session: AsyncSession,
    *,
    document,
) -> dict[str, Any]:
    """Resolve process rule JSON for one document."""

    from app.dataset.domain.constants import DEFAULT_PROCESS_RULE

    loaded = await load_document_process_rule_for_detail(session, document=document)
    if loaded is None:
        return DEFAULT_PROCESS_RULE
    return loaded
