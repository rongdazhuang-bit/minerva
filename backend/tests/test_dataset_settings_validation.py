"""Unit tests for dataset settings validation."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock

import pytest

from app.dataset.domain.constants import INDEXING_STATUS_COMPLETED, INDEXING_TECHNIQUE_HIGH_QUALITY
from app.dataset.service import dataset_service
from app.dataset.service.dataset_service import _assert_embedding_change_allowed
from app.exceptions import AppError


@pytest.mark.asyncio
async def test_embedding_change_forbidden_when_completed_docs_exist(monkeypatch) -> None:
    """Changing embedding model is blocked after successful indexing."""

    session = AsyncMock()
    row = type(
        "DatasetStub",
        (),
        {
            "id": uuid.uuid4(),
            "indexing_technique": INDEXING_TECHNIQUE_HIGH_QUALITY,
            "embedding_model": "text-embedding-3-small",
            "embedding_model_provider": "openai",
        },
    )()

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 2

    monkeypatch.setattr(dataset_service.repo, "count_documents_by_status", fake_count)

    with pytest.raises(AppError) as exc:
        await _assert_embedding_change_allowed(
            session,
            row=row,
            patch={"embedding_model": "other-model"},
        )
    assert exc.value.code == "dataset.embedding_change_forbidden"


@pytest.mark.asyncio
async def test_embedding_change_allowed_without_completed_docs(monkeypatch) -> None:
    """Embedding model can change when no completed documents exist."""

    session = AsyncMock()
    row = type(
        "DatasetStub",
        (),
        {
            "id": uuid.uuid4(),
            "indexing_technique": INDEXING_TECHNIQUE_HIGH_QUALITY,
            "embedding_model": "text-embedding-3-small",
            "embedding_model_provider": "openai",
        },
    )()

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 0

    monkeypatch.setattr(dataset_service.repo, "count_documents_by_status", fake_count)

    await _assert_embedding_change_allowed(
        session,
        row=row,
        patch={"embedding_model": "other-model"},
    )
