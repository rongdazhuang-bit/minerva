"""Optional end-to-end tests for dataset ingestion (requires live services)."""

from __future__ import annotations

import os

import pytest

from app.dataset.domain.constants import DEFAULT_PROCESS_RULE
from app.dataset.rag.index_processor import build_index_units


def _integration_env_ready() -> bool:
    if os.getenv("RUN_DATASET_INTEGRATION") != "1":
        return False
    if not os.getenv("SYNC_DATABASE_URL") and not os.getenv("DATABASE_URL"):
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _integration_env_ready(),
    reason=(
        "Set RUN_DATASET_INTEGRATION=1 plus DATABASE_URL, Celery worker on queue=dataset, "
        "pgvector, and an enabled EMBEDDINGS model."
    ),
)


def test_hierarchical_units_smoke_under_integration_flag() -> None:
    """Sanity check index processor when integration suite is enabled."""

    units = build_index_units(
        "paragraph one\n\nparagraph two",
        doc_form="hierarchical_model",
        process_rule=DEFAULT_PROCESS_RULE,
    )
    assert units
    assert units[0].children


@pytest.mark.asyncio
async def test_dataset_integration_full_flow_placeholder() -> None:
    """Reserved for upload → init → hit-testing against a live stack."""

    pytest.skip(
        "Implement with authenticated httpx client against MINERVA_API_URL when CI stack is available."
    )
