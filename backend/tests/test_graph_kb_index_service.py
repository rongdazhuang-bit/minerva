"""GraphKB index enqueue conflict, projection mapping, and secret redaction."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest

from app.exceptions import AppError
from app.graph_kb.domain.constants import (
    JOB_CLEANUP,
    JOB_INDEX,
    JOB_REINDEX,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
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


def test_send_index_task_raises_when_celery_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Missing Celery must raise so enqueue_index can mark the job failed."""

    from app.graph_kb.service import index_service as idx
    import app.celery_app as celery_mod

    monkeypatch.setattr(celery_mod, "celery_app", None)
    with pytest.raises(RuntimeError):
        idx._send_index_task(uuid4())


@pytest.mark.asyncio
async def test_enqueue_index_marks_failed_when_send_task_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A send_task failure after insert must persist failed, not leave pending."""

    from app.graph_kb.service import index_service as idx

    graph = SimpleNamespace(
        id=uuid4(),
        workspace_id=uuid4(),
        indexing_status="empty",
    )
    job_box: dict = {}

    class _Result:
        """Stand-in for ``session.scalars(...).all()``."""

        def all(self) -> list:
            return []

    class _Session:
        """Minimal async session for enqueue_index."""

        def add(self, obj) -> None:
            job_box["job"] = obj

        async def scalar(self, *_a, **_k):
            return graph

        async def scalars(self, *_a, **_k):
            return _Result()

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            return None

        async def refresh(self, _obj) -> None:
            return None

    monkeypatch.setattr(
        idx,
        "_send_index_task",
        lambda _jid: (_ for _ in ()).throw(RuntimeError("broker down")),
    )

    with pytest.raises(AppError) as exc:
        await idx.enqueue_index(
            _Session(),
            workspace_id=graph.workspace_id,
            graph_id=graph.id,
            user_id=uuid4(),
        )
    assert exc.value.status_code == 503
    assert exc.value.code == "graph_kb.enqueue_failed"
    assert job_box["job"].status == STATUS_FAILED
    assert graph.indexing_status == STATUS_FAILED
    assert job_box["job"].finished_at is not None


@pytest.mark.asyncio
async def test_run_index_job_persists_started_at_on_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """After rollback, failed jobs must keep started_at plus finished_at and error."""

    from datetime import UTC, datetime

    from app.graph_kb.service import index_service as idx

    job_id = uuid4()
    workspace_id = uuid4()
    graph_id = uuid4()
    started = datetime(2026, 8, 23, 10, 0, tzinfo=UTC)
    job = SimpleNamespace(
        id=job_id,
        workspace_id=workspace_id,
        graph_id=graph_id,
        status=STATUS_PENDING,
        started_at=None,
        finished_at=None,
        error=None,
    )
    graph = SimpleNamespace(
        id=graph_id,
        workspace_id=workspace_id,
        engine="lightrag",
        indexing_status=STATUS_PENDING,
    )
    commits: list[str] = []

    class _Result:
        """Stand-in for ``session.scalars(...).all()``."""

        def all(self) -> list:
            return []

    class _Session:
        """Minimal async session for run_index_job."""

        async def get(self, _cls, _id):
            return job

        async def scalar(self, *_a, **_k):
            return graph

        async def scalars(self, *_a, **_k):
            return _Result()

        async def flush(self) -> None:
            return None

        async def commit(self) -> None:
            commits.append(job.status)

        async def rollback(self) -> None:
            return None

    class _BoomClient:
        """Fail on Worker index after running status is committed."""

        async def index(self, _req):
            raise RuntimeError("worker down")

    monkeypatch.setattr(idx, "create_engine_client", lambda: _BoomClient())

    class _Dt:
        """Clock that returns a fixed ``started`` timestamp."""

        @staticmethod
        def now(*, tz=None):
            return started

    monkeypatch.setattr(idx, "datetime", _Dt)

    result = await idx.run_index_job(_Session(), job_id=job_id)
    assert result["status"] == STATUS_FAILED
    assert job.status == STATUS_FAILED
    assert job.started_at == started
    assert job.finished_at == started
    assert job.error
    assert STATUS_RUNNING in commits
    assert commits[0] == STATUS_RUNNING


def test_resolve_graph_kb_data_defaults_to_backend_data() -> None:
    """Unset GRAPH_KB_DATA must resolve to backend/data/graph_kb."""

    from app.config import Settings, _BACKEND_DIR

    settings = Settings.model_construct(graph_kb_data="")
    assert settings.resolve_graph_kb_data() == (_BACKEND_DIR / "data" / "graph_kb").resolve()
