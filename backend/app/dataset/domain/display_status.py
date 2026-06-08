"""Display status helpers for dataset documents."""

from __future__ import annotations

from app.dataset.domain.constants import INDEXING_STATUS_COMPLETED, INDEXING_STATUS_ERROR
from app.dataset.domain.db.models import DatasetDocument


def compute_display_status(document: DatasetDocument) -> str:
    """Map document row fields to a UI-friendly status slug."""

    if document.archived:
        return "archived"
    if document.is_paused:
        return "paused"
    if document.indexing_status == INDEXING_STATUS_ERROR:
        return "error"
    if document.indexing_status != INDEXING_STATUS_COMPLETED:
        return "indexing"
    if not document.enabled:
        return "disabled"
    return "available"
