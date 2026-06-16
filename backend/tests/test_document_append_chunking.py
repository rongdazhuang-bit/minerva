"""Tests for append documents with per-document process_rule rows."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.dataset.domain.constants import INDEXING_STATUS_WAITING
from app.dataset.domain.db.models import DatasetDocument, DatasetProcessRule
from app.dataset.service import document_service


def _dataset_stub(**overrides):
    """Build a minimal dataset stub for append_documents tests."""

    defaults = {
        "id": uuid.uuid4(),
        "chunk_structure": "text_model",
    }
    defaults.update(overrides)
    return type("DatasetStub", (), defaults)()


def _upload_stub(upload_id: uuid.UUID, workspace_id: uuid.UUID, name: str = "demo.txt"):
    """Build a minimal upload file stub."""

    return type(
        "UploadStub",
        (),
        {"id": upload_id, "workspace_id": workspace_id, "name": name},
    )()


@pytest.mark.asyncio
async def test_append_with_process_rule_creates_rule_per_document(monkeypatch) -> None:
    """Each appended document gets its own DatasetProcessRule row."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    file_id_a = uuid.uuid4()
    file_id_b = uuid.uuid4()
    dataset = _dataset_stub(id=dataset_id)
    added: list = []

    session.add = MagicMock(side_effect=lambda row: added.append(row))

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 0

    async def fake_max_pos(*args, **kwargs):
        _ = args, kwargs
        return 0

    uploads = {
        file_id_a: _upload_stub(file_id_a, workspace_id, "a.txt"),
        file_id_b: _upload_stub(file_id_b, workspace_id, "b.txt"),
    }

    async def fake_get_upload(session_obj, upload_id):
        _ = session_obj
        return uploads.get(upload_id)

    session.get = AsyncMock(side_effect=fake_get_upload)

    enqueue_ids: list[uuid.UUID] = []

    def fake_enqueue(ds_id, doc_ids):
        _ = ds_id
        enqueue_ids.extend(doc_ids)

    monkeypatch.setattr(document_service, "require_dataset", fake_require)
    monkeypatch.setattr(document_service.repo, "count_documents_for_dataset", fake_count)
    monkeypatch.setattr(document_service.repo, "max_document_position", fake_max_pos)
    monkeypatch.setattr(document_service, "_enqueue_indexing", fake_enqueue)

    process_rule = {
        "mode": "custom",
        "rules": {"segmentation": {"delimiter": "\n\n", "max_length": 800}},
    }

    result = await document_service.append_documents(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset_id=dataset_id,
        file_ids=[file_id_a, file_id_b],
        process_rule=process_rule,
    )

    rule_rows = [row for row in added if isinstance(row, DatasetProcessRule)]
    doc_rows = [row for row in added if isinstance(row, DatasetDocument)]

    assert len(rule_rows) == 2
    assert len(doc_rows) == 2
    assert rule_rows[0].id != rule_rows[1].id
    assert doc_rows[0].dataset_process_rule_id == rule_rows[0].id
    assert doc_rows[1].dataset_process_rule_id == rule_rows[1].id
    assert doc_rows[0].dataset_process_rule_id != doc_rows[1].dataset_process_rule_id
    assert doc_rows[0].indexing_status == INDEXING_STATUS_WAITING
    assert doc_rows[1].indexing_status == INDEXING_STATUS_WAITING
    assert len(enqueue_ids) == 2
    assert len(result["documents"]) == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_append_without_process_rule_uses_latest_rule(monkeypatch) -> None:
    """Omitting process_rule keeps existing latest-rule behavior."""

    session = AsyncMock()
    workspace_id = uuid.uuid4()
    user_id = uuid.uuid4()
    dataset_id = uuid.uuid4()
    file_id = uuid.uuid4()
    dataset = _dataset_stub(id=dataset_id)
    latest_rule = type("RuleStub", (), {"id": uuid.uuid4()})()
    added: list = []

    session.add = MagicMock(side_effect=lambda row: added.append(row))

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 0

    async def fake_max_pos(*args, **kwargs):
        _ = args, kwargs
        return 0

    async def fake_latest(*args, **kwargs):
        _ = args, kwargs
        return latest_rule

    session.get = AsyncMock(return_value=_upload_stub(file_id, workspace_id))

    monkeypatch.setattr(document_service, "require_dataset", fake_require)
    monkeypatch.setattr(document_service.repo, "count_documents_for_dataset", fake_count)
    monkeypatch.setattr(document_service.repo, "max_document_position", fake_max_pos)
    monkeypatch.setattr(document_service.repo, "get_latest_process_rule", fake_latest)
    monkeypatch.setattr(document_service, "_enqueue_indexing", lambda *_: None)

    await document_service.append_documents(
        session,
        workspace_id=workspace_id,
        user_id=user_id,
        dataset_id=dataset_id,
        file_ids=[file_id],
        process_rule=None,
    )

    rule_rows = [row for row in added if isinstance(row, DatasetProcessRule)]
    doc_rows = [row for row in added if isinstance(row, DatasetDocument)]
    assert len(rule_rows) == 0
    assert len(doc_rows) == 1
    assert doc_rows[0].dataset_process_rule_id == latest_rule.id
