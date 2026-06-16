"""Tests for document-level process_rule patch and reprocess."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dataset.domain.constants import INDEXING_STATUS_COMPLETED, INDEXING_STATUS_WAITING
from app.dataset.service import document_service
from app.exceptions import AppError


def _document_stub(**overrides):
    """Build a minimal document stub for update_document tests."""

    defaults = {
        "id": uuid.uuid4(),
        "dataset_id": uuid.uuid4(),
        "name": "demo.txt",
        "archived": False,
        "created_by": uuid.uuid4(),
        "dataset_process_rule_id": uuid.uuid4(),
        "indexing_status": INDEXING_STATUS_COMPLETED,
        "position": 1,
        "enabled": True,
        "is_paused": False,
        "error": None,
        "batch": "batch",
        "doc_form": "text_model",
        "word_count": 100,
        "create_at": None,
        "update_at": None,
        "completed_at": None,
        "processing_started_at": None,
        "parsing_completed_at": None,
        "cleaning_completed_at": None,
        "splitting_completed_at": None,
    }
    defaults.update(overrides)
    return type("DocumentStub", (), defaults)()


@pytest.mark.asyncio
async def test_patch_document_process_rule_creates_new_rule_row(monkeypatch) -> None:
    """PATCH process_rule creates a new dataset_process_rule row and links the document."""

    workspace_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    document_id = uuid.uuid4()
    user_id = uuid.uuid4()
    document = _document_stub(id=document_id, dataset_id=dataset_id)
    old_rule_id = document.dataset_process_rule_id
    added: list = []

    def capture_add(row):
        added.append(row)

    session = AsyncMock()
    session.add = MagicMock(side_effect=capture_add)

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    dataset = type("DatasetStub", (), {"id": dataset_id})()

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    reprocess_called = False

    async def fake_reprocess(*args, **kwargs):
        nonlocal reprocess_called
        reprocess_called = True
        _ = args, kwargs

    enqueue_called: list[uuid.UUID] = []

    def fake_enqueue(ds_id, doc_ids):
        enqueue_called.extend(doc_ids)

    monkeypatch.setattr(document_service.repo, "get_document_for_dataset", fake_get_doc)
    monkeypatch.setattr(document_service, "require_dataset", fake_require)
    monkeypatch.setattr(document_service, "reprocess_document", fake_reprocess)
    monkeypatch.setattr(document_service, "_enqueue_indexing", fake_enqueue)

    process_rule = {"mode": "custom", "rules": {"segmentation": {"delimiter": "\n", "max_length": 500}}}
    await document_service.update_document(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        user_id=user_id,
        patch={"process_rule": process_rule},
    )

    assert len(added) == 1
    assert added[0].dataset_id == dataset_id
    assert added[0].created_by == user_id
    assert document.dataset_process_rule_id != old_rule_id
    assert document.dataset_process_rule_id == added[0].id
    assert reprocess_called is True
    assert enqueue_called == [document_id]
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_patch_document_process_rule_triggers_reindex(monkeypatch) -> None:
    """PATCH process_rule resets indexing_status to waiting."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    document_id = uuid.uuid4()
    document = _document_stub(
        id=document_id,
        dataset_id=dataset_id,
        indexing_status=INDEXING_STATUS_COMPLETED,
    )

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    dataset = type("DatasetStub", (), {"id": dataset_id})()

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_delete_vectors(*args, **kwargs):
        _ = args, kwargs

    async def fake_delete_segments(*args, **kwargs):
        _ = args, kwargs

    monkeypatch.setattr(document_service.repo, "get_document_for_dataset", fake_get_doc)
    monkeypatch.setattr(document_service, "require_dataset", fake_require)
    monkeypatch.setattr(document_service, "delete_vector_nodes_for_document", fake_delete_vectors)
    monkeypatch.setattr(document_service, "delete_segments_for_document", fake_delete_segments)
    monkeypatch.setattr(document_service, "_enqueue_indexing", lambda *_a, **_k: None)

    await document_service.update_document(
        session,
        workspace_id=workspace_id,
        dataset_id=dataset_id,
        document_id=document_id,
        user_id=uuid.uuid4(),
        patch={"process_rule": {"mode": "custom", "rules": {}}},
    )

    assert document.indexing_status == INDEXING_STATUS_WAITING
    assert document.completed_at is None


@pytest.mark.asyncio
async def test_patch_archived_document_process_rule_rejected(monkeypatch) -> None:
    """Archived documents cannot update process_rule."""

    session = AsyncMock()
    document = _document_stub(archived=True)

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    monkeypatch.setattr(document_service.repo, "get_document_for_dataset", fake_get_doc)

    with pytest.raises(AppError) as exc:
        await document_service.update_document(
            session,
            workspace_id=uuid.uuid4(),
            dataset_id=uuid.uuid4(),
            document_id=document.id,
            user_id=uuid.uuid4(),
            patch={"process_rule": {"mode": "custom", "rules": {}}},
        )
    assert exc.value.code == "dataset.document_archived"


@pytest.mark.asyncio
async def test_patch_document_name_only_no_reprocess(monkeypatch) -> None:
    """Renaming a document does not trigger reprocess or rule creation."""

    session = AsyncMock()
    document = _document_stub(indexing_status=INDEXING_STATUS_COMPLETED)
    added: list = []

    session.add.side_effect = lambda row: added.append(row)

    async def fake_get_doc(*args, **kwargs):
        _ = args, kwargs
        return document

    reprocess_called = False

    async def fake_reprocess(*args, **kwargs):
        nonlocal reprocess_called
        reprocess_called = True
        _ = args, kwargs

    enqueue_called = False

    def fake_enqueue(*args, **kwargs):
        nonlocal enqueue_called
        enqueue_called = True

    monkeypatch.setattr(document_service.repo, "get_document_for_dataset", fake_get_doc)
    monkeypatch.setattr(document_service, "reprocess_document", fake_reprocess)
    monkeypatch.setattr(document_service, "_enqueue_indexing", fake_enqueue)

    await document_service.update_document(
        session,
        workspace_id=uuid.uuid4(),
        dataset_id=uuid.uuid4(),
        document_id=document.id,
        user_id=uuid.uuid4(),
        patch={"name": "renamed.txt"},
    )

    assert document.name == "renamed.txt"
    assert added == []
    assert reprocess_called is False
    assert enqueue_called is False
    assert document.indexing_status == INDEXING_STATUS_COMPLETED
