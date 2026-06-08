"""Tests for Dify-aligned missing dataset API handlers."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.dataset.domain.constants import DOC_FORM_HIERARCHICAL, INDEXING_STATUS_PARSING
from app.dataset.service import dataset_service, document_service, segment_service
from app.exceptions import AppError


@pytest.mark.asyncio
async def test_create_empty_dataset_persists_default_rule(monkeypatch) -> None:
    """POST /datasets creates kb with default process rule."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    dataset_id = uuid.uuid4()

    async def fake_detail(*args, **kwargs):
        _ = args, kwargs
        return {"id": dataset_id, "name": "Empty KB", "document_count": 0}

    monkeypatch.setattr(dataset_service, "get_dataset_detail", fake_detail)

    payload = await dataset_service.create_empty_dataset(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        name="Empty KB",
    )
    assert payload["id"] == dataset_id
    assert session.add.call_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_document_indexing_status_includes_segment_counts(monkeypatch) -> None:
    """GET document indexing-status returns segment progress fields."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    document_id = uuid.uuid4()
    document = type(
        "DocumentStub",
        (),
        {
            "id": document_id,
            "name": "demo.txt",
            "indexing_status": INDEXING_STATUS_PARSING,
            "enabled": True,
            "archived": False,
            "is_paused": False,
            "error": None,
            "processing_started_at": None,
            "parsing_completed_at": None,
            "cleaning_completed_at": None,
            "splitting_completed_at": None,
            "completed_at": None,
            "stopped_at": None,
        },
    )()

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 5, 2

    monkeypatch.setattr(document_service.repo, "get_document_for_dataset", fake_get_doc)
    monkeypatch.setattr(document_service.repo, "count_segments_for_document", fake_count)

    payload = await document_service.get_document_indexing_status(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
    )
    assert payload["indexing_status"] == INDEXING_STATUS_PARSING
    assert payload["total_segments"] == 5
    assert payload["completed_segments"] == 2


@pytest.mark.asyncio
async def test_create_child_chunk_rejects_non_hierarchical(monkeypatch) -> None:
    """Child chunk APIs require hierarchical doc_form."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    document_id = uuid.uuid4()
    segment_id = uuid.uuid4()

    dataset = type("DatasetStub", (), {"chunk_structure": "text_model"})()
    document = type("DocumentStub", (), {"doc_form": "text_model", "created_by": uuid.uuid4()})()

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    monkeypatch.setattr(segment_service, "require_dataset", fake_require)
    monkeypatch.setattr(segment_service.repo, "get_document_for_dataset", fake_get_doc)

    with pytest.raises(AppError) as exc:
        await segment_service.create_child_chunk(
            session,
            workspace_id=workspace_id,
            dataset_id=dataset_id,
            document_id=document_id,
            segment_id=segment_id,
            user_id=uuid.uuid4(),
            content="child text",
        )
    assert exc.value.code == "dataset.child_chunk_not_supported"


@pytest.mark.asyncio
async def test_create_child_chunk_indexes_customized_row(monkeypatch) -> None:
    """POST child_chunks creates row with type customized and syncs index."""

    session = AsyncMock()
    session.flush = AsyncMock()
    workspace_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    document_id = uuid.uuid4()
    segment_id = uuid.uuid4()
    user_id = uuid.uuid4()

    dataset = type(
        "DatasetStub",
        (),
        {"chunk_structure": DOC_FORM_HIERARCHICAL, "indexing_technique": "economy"},
    )()
    document = type("DocumentStub", (), {"doc_form": DOC_FORM_HIERARCHICAL, "created_by": user_id})()
    segment = type("SegmentStub", (), {"id": segment_id})()

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    async def fake_get_segment(*args, **kwargs):
        _ = args, kwargs
        return segment

    async def fake_max_pos(*args, **kwargs):
        _ = args, kwargs
        return 1

    async def fake_sync(*args, **kwargs):
        _ = args, kwargs

    added: list = []
    session.add = added.append

    monkeypatch.setattr(segment_service, "require_dataset", fake_require)
    monkeypatch.setattr(segment_service.repo, "get_document_for_dataset", fake_get_doc)
    monkeypatch.setattr(segment_service.repo, "get_segment_for_document", fake_get_segment)
    monkeypatch.setattr(segment_service.repo, "max_child_chunk_position", fake_max_pos)
    monkeypatch.setattr(segment_service, "sync_child_chunk_index", fake_sync)

    payload = await segment_service.create_child_chunk(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        segment_id=segment_id,
        user_id=user_id,
        content="custom child",
    )
    assert payload["content"] == "custom child"
    assert len(added) == 1
    assert added[0].type == "customized"
    assert added[0].position == 2
