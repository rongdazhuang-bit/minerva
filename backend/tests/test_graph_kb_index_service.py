"""GraphKB index enqueue conflict, projection mapping, and secret redaction."""

from __future__ import annotations

from uuid import UUID

from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    JOB_CLEANUP,
    JOB_INDEX,
    JOB_REINDEX,
    STATUS_COMPLETED,
    STATUS_RUNNING,
)
from app.graph_kb.engine.types import SummaryItem
from app.graph_kb.service.index_service import assert_no_active_index_job, redact_secret
from app.graph_kb.service.projection_service import summaries_to_rows


def test_conflict() -> None:
    """Pending/running index jobs must raise 409 graph_kb.job_conflict."""

    try:
        assert_no_active_index_job([{"kind": JOB_INDEX, "status": STATUS_RUNNING}])
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "graph_kb.job_conflict"
    else:
        raise AssertionError("expected conflict")


def test_reindex_running_conflicts() -> None:
    """A running reindex job also blocks a new index enqueue."""

    try:
        assert_no_active_index_job([{"kind": JOB_REINDEX, "status": STATUS_RUNNING}])
    except AppError as exc:
        assert exc.status_code == 409
        assert exc.code == "graph_kb.job_conflict"
    else:
        raise AssertionError("expected conflict")


def test_completed_index_is_not_conflict() -> None:
    """Finished index jobs must not block a later enqueue."""

    assert_no_active_index_job([{"kind": JOB_INDEX, "status": STATUS_COMPLETED}])


def test_running_cleanup_is_not_index_conflict() -> None:
    """Cleanup jobs are a different kind and do not conflict with index."""

    assert_no_active_index_job([{"kind": JOB_CLEANUP, "status": STATUS_RUNNING}])


def test_summaries_to_rows() -> None:
    """Map SummaryItem fields onto projection-row dicts without a DB."""

    workspace_id = UUID("11111111-1111-1111-1111-111111111111")
    graph_id = UUID("22222222-2222-2222-2222-222222222222")
    items = [
        SummaryItem(
            summary_id="c1",
            title="Topic",
            content="body",
            level=1,
            parent_id=None,
        )
    ]
    rows = summaries_to_rows(items, graph_id=graph_id, workspace_id=workspace_id)
    assert len(rows) == 1
    assert rows[0]["engine_community_id"] == "c1"
    assert rows[0]["title"] == "Topic"
    assert rows[0]["summary"] == "body"
    assert rows[0]["level"] == 1
    assert rows[0]["parent_id"] is None
    assert rows[0]["graph_id"] == graph_id
    assert rows[0]["workspace_id"] == workspace_id


def test_redact_secret_keeps_last_four_or_stars() -> None:
    """Long secrets keep the last four characters; short ones become ***."""

    assert redact_secret("sk-abcdefghij") == "***ghij"
    assert redact_secret("abcd") == "***"
    assert redact_secret("") == "***"
    assert redact_secret(None) == "***"
