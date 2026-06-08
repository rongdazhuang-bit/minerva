"""Unit tests for dataset display status mapping."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from app.dataset.domain.constants import INDEXING_STATUS_COMPLETED, INDEXING_STATUS_ERROR
from app.dataset.domain.db.models import DatasetDocument
from app.dataset.domain.display_status import compute_display_status


def _doc(**kwargs) -> DatasetDocument:
    """Build a minimal document row for status tests."""

    defaults = {
        "id": uuid.uuid4(),
        "workspace_id": uuid.uuid4(),
        "dataset_id": uuid.uuid4(),
        "position": 1,
        "data_source_type": "upload_file",
        "batch": "batch",
        "name": "a.txt",
        "created_from": "web",
        "created_by": uuid.uuid4(),
        "indexing_status": INDEXING_STATUS_COMPLETED,
        "enabled": True,
        "archived": False,
        "is_paused": False,
        "doc_form": "text_model",
        "create_at": datetime.now(tz=UTC),
    }
    defaults.update(kwargs)
    return DatasetDocument(**defaults)


def test_display_status_available_when_completed_and_enabled() -> None:
    """Completed enabled documents are available."""

    assert compute_display_status(_doc()) == "available"


def test_display_status_indexing_when_not_completed() -> None:
    """Non-completed documents show indexing."""

    assert compute_display_status(_doc(indexing_status="parsing")) == "indexing"


def test_display_status_error() -> None:
    """Error status maps to error."""

    assert compute_display_status(_doc(indexing_status=INDEXING_STATUS_ERROR)) == "error"


def test_display_status_disabled() -> None:
    """Disabled completed documents are disabled."""

    assert compute_display_status(_doc(enabled=False)) == "disabled"
