"""Tests for dataset detail payload including process_rule."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import pytest

from app.dataset.service.dataset_service import get_dataset_detail


@pytest.mark.asyncio
async def test_get_dataset_detail_includes_deserialized_process_rule(monkeypatch) -> None:
    """Detail API payload exposes latest process_rule JSON."""

    dataset_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    rule_id = uuid.uuid4()
    rule_json = {
        "mode": "custom",
        "rules": {
            "segmentation": {"delimiter": "\\n\\n", "max_length": 512, "chunk_overlap": 20},
            "parent_mode": {"delimiter": "\\n\\n", "max_length": 2000, "chunk_overlap": 100},
        },
    }

    dataset_row = type(
        "DatasetStub",
        (),
        {
            "id": dataset_id,
            "name": "Demo KB",
            "description": None,
            "indexing_technique": "high_quality",
            "embedding_model": "text-embedding-3-small",
            "embedding_model_provider": "openai",
            "retrieval_model": {},
            "chunk_structure": "hierarchical_model",
            "create_at": None,
            "update_at": None,
        },
    )()
    process_row = type(
        "ProcessRuleStub",
        (),
        {"id": rule_id, "rules": json.dumps(rule_json, ensure_ascii=False)},
    )()

    session = AsyncMock()

    async def fake_require(*args, **kwargs):
        _ = args, kwargs
        return dataset_row

    async def fake_count(*args, **kwargs):
        _ = args, kwargs
        return 3

    async def fake_latest(*args, **kwargs):
        _ = args, kwargs
        return process_row

    monkeypatch.setattr("app.dataset.service.dataset_service.require_dataset", fake_require)
    monkeypatch.setattr("app.dataset.service.dataset_service.repo.count_documents_for_dataset", fake_count)
    monkeypatch.setattr("app.dataset.service.dataset_service.repo.get_latest_process_rule", fake_latest)

    payload = await get_dataset_detail(session, workspace_id=workspace_id, dataset_id=dataset_id)
    assert payload["process_rule_id"] == rule_id
    assert payload["process_rule"]["rules"]["segmentation"]["max_length"] == 512
    assert payload["process_rule"]["rules"]["parent_mode"]["max_length"] == 2000
