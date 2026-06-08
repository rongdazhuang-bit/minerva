"""Unit tests for hierarchical segment index sync."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.dataset.domain.constants import (
    DOC_FORM_HIERARCHICAL,
    INDEXING_TECHNIQUE_ECONOMY,
)
from app.dataset.rag.index_processor import split_children_for_parent
from app.dataset.service.index_sync_service import sync_segment_indexes


def test_split_children_for_parent_uses_subchunk_rules() -> None:
    """One parent body splits into multiple child texts."""

    parent = "alpha beta gamma delta"
    children = split_children_for_parent(
        parent,
        process_rule={
            "rules": {
                "subchunk_segmentation": {"delimiter": " ", "max_length": 10, "chunk_overlap": 0},
            }
        },
    )
    assert len(children) >= 2
    assert all(child.strip() for child in children)


@pytest.mark.asyncio
async def test_sync_segment_indexes_creates_child_chunks_for_hierarchical(monkeypatch) -> None:
    """Manual segment CRUD rebuilds child rows in hierarchical mode."""

    session = AsyncMock()
    session.flush = AsyncMock()
    dataset_id = uuid.uuid4()
    document_id = uuid.uuid4()
    segment_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()

    dataset = type(
        "DatasetStub",
        (),
        {
            "id": dataset_id,
            "workspace_id": workspace_id,
            "indexing_technique": INDEXING_TECHNIQUE_ECONOMY,
            "keyword_number": 5,
            "chunk_structure": DOC_FORM_HIERARCHICAL,
            "embedding_model": None,
            "embedding_model_provider": None,
        },
    )()
    document = type(
        "DocumentStub",
        (),
        {
            "id": document_id,
            "doc_form": DOC_FORM_HIERARCHICAL,
            "dataset_process_rule_id": None,
            "created_by": user_id,
        },
    )()
    segment = type(
        "SegmentStub",
        (),
        {
            "id": segment_id,
            "content": "part one part two part three",
            "index_node_id": None,
            "status": "waiting",
        },
    )()

    added_children: list = []

    def capture_add(row) -> None:
        if getattr(row, "segment_id", None) == segment_id:
            added_children.append(row)

    session.add = capture_add

    async def fake_load_rule(*args, **kwargs):
        _ = args, kwargs
        return {
            "rules": {
                "subchunk_segmentation": {"delimiter": " ", "max_length": 10, "chunk_overlap": 0},
            }
        }

    async def fake_list_children(*args, **kwargs):
        _ = args, kwargs
        return []

    async def fake_add_keywords(*args, **kwargs):
        _ = args, kwargs

    async def fake_load_table(*args, **kwargs):
        _ = args, kwargs
        return {}

    async def fake_save_table(*args, **kwargs):
        _ = args, kwargs

    monkeypatch.setattr(
        "app.dataset.service.index_sync_service.load_document_process_rule",
        fake_load_rule,
    )
    monkeypatch.setattr(
        "app.dataset.service.index_sync_service.repo.list_child_chunks_for_segment",
        fake_list_children,
    )
    monkeypatch.setattr(
        "app.dataset.service.index_sync_service.add_segment_keywords",
        fake_add_keywords,
    )
    monkeypatch.setattr(
        "app.dataset.service.index_sync_service._load_keyword_table",
        fake_load_table,
    )
    monkeypatch.setattr(
        "app.dataset.service.index_sync_service._save_keyword_table",
        fake_save_table,
    )

    child_count = await sync_segment_indexes(
        session,
        dataset=dataset,
        document=document,
        segment=segment,
        user_id=user_id,
    )

    assert child_count >= 2
    assert len(added_children) == child_count
    assert segment.status == "completed"
