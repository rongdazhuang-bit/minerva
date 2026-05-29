"""Tests for MODEL_TAG validation on sys_models."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import AppError
from app.sys.model_provider.service import model_provider_service as svc


@pytest.mark.asyncio
async def test_normalize_tags_dedupes_and_sorts() -> None:
    """Duplicate and padded tag codes normalize to a sorted unique list."""

    session = AsyncMock()
    with patch.object(
        svc,
        "_load_dict_code_set",
        new=AsyncMock(return_value={"TEXT", "EMBEDDINGS"}),
    ):
        out = await svc.normalize_tags(
            session,
            workspace_id=uuid.uuid4(),
            tags=["EMBEDDINGS", "TEXT", "TEXT", "  TEXT  "],
        )
    assert out == ["EMBEDDINGS", "TEXT"]


@pytest.mark.asyncio
async def test_normalize_tags_rejects_empty() -> None:
    """Empty tag lists are rejected before dictionary lookup."""

    session = AsyncMock()
    with pytest.raises(AppError) as exc:
        await svc.normalize_tags(session, workspace_id=uuid.uuid4(), tags=[])
    assert exc.value.code == "model_provider.tags_required"


@pytest.mark.asyncio
async def test_normalize_tags_rejects_unknown_code() -> None:
    """Tag codes not in MODEL_TAG dictionary raise tag_invalid."""

    session = AsyncMock()
    with patch.object(
        svc,
        "_load_dict_code_set",
        new=AsyncMock(return_value={"TEXT"}),
    ):
        with pytest.raises(AppError) as exc:
            await svc.normalize_tags(
                session, workspace_id=uuid.uuid4(), tags=["TEXT", "NOPE"]
            )
    assert exc.value.code == "model_provider.tag_invalid"
