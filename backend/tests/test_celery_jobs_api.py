"""Integration and persistence tests for workspace celery job APIs."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import jwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import app.domain.identity.models  # noqa: F401
from app.config import settings
from app.infrastructure.db.session import async_session_factory, engine
from app.main import app
from app import celery_app as celery_runtime
from app.sys.celery.domain.db.models import SysCelery
from app.sys.celery.service import celery_schedule_service


async def _prepare_workspace() -> uuid.UUID:
    """Create a tenant/workspace pair and return the workspace id."""

    tenant_id = uuid.uuid4()
    workspace_id = uuid.uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            text(
                """
                INSERT INTO tenants (id, name, slug)
                VALUES (:id, :name, :slug)
                """
            ),
            {"id": tenant_id, "name": "Celery Tenant", "slug": f"celery-{tenant_id.hex}"},
        )
        await conn.execute(
            text(
                """
                INSERT INTO workspaces (id, tenant_id, name, slug)
                VALUES (:id, :tenant_id, :name, :slug)
                """
            ),
            {
                "id": workspace_id,
                "tenant_id": tenant_id,
                "name": "Celery Workspace",
                "slug": f"celery-ws-{workspace_id.hex}",
            },
        )
        await conn.run_sync(SysCelery.__table__.drop, checkfirst=True)
        await conn.run_sync(SysCelery.__table__.create, checkfirst=True)
    return workspace_id


async def _cleanup_workspace(workspace_id: uuid.UUID) -> None:
    """Delete rows created by this test to keep database reusable."""

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM sys_celery WHERE workspace_id = :workspace_id"), {"workspace_id": workspace_id})
        await conn.execute(text("DELETE FROM workspaces WHERE id = :workspace_id"), {"workspace_id": workspace_id})
        await conn.execute(
            text(
                """
                DELETE FROM tenants
                WHERE id NOT IN (SELECT tenant_id FROM workspaces)
                """
            )
        )


def _workspace_id_from_access_token(access_token: str) -> str:
    """Decode workspace id claim from access JWT."""

    payload = jwt.decode(access_token, settings.jwt_secret, algorithms=["HS256"])
    return str(payload["wid"])


async def _ensure_celery_table_exists() -> None:
    """Ensure ``sys_celery`` table exists for API integration tests."""

    async with engine.begin() as conn:
        await conn.run_sync(SysCelery.__table__.create, checkfirst=True)


async def _register_workspace_user(client: AsyncClient) -> tuple[str, str, dict[str, str]]:
    """Create one user/workspace by register API and return auth context."""

    email = f"celery-api-{uuid.uuid4().hex}@example.com"
    register = await client.post(
        "/auth/register",
        json={"email": email, "password": "secret1234"},
    )
    assert register.status_code == 201, register.text
    token = register.json()["access_token"]
    workspace_id = _workspace_id_from_access_token(token)
    return token, workspace_id, {"Authorization": f"Bearer {token}"}


async def _create_job(
    client: AsyncClient,
    *,
    workspace_id: str,
    headers: dict[str, str],
) -> dict:
    """Create a job through API and return created row payload."""

    payload = {
        "name": "nightly-report",
        "task_code": "report.daily",
        "task": "app.tasks.report_daily",
        "cron": "0 8 * * *",
        "args_json": ["daily"],
        "kwargs_json": {"force": True},
        "timezone": "Asia/Shanghai",
        "enabled": True,
        "status": "Y",
        "remark": "nightly run",
    }
    created = await client.post(
        f"/workspaces/{workspace_id}/celery-jobs",
        headers=headers,
        json=payload,
    )
    assert created.status_code == 201, created.text
    return created.json()


@pytest.mark.asyncio
async def test_create_job_persists_extended_fields() -> None:
    """Create one schedule job and verify extended sys_celery fields round-trip."""

    workspace_id = await _prepare_workspace()
    next_run_at = datetime(2026, 5, 1, 8, 0, tzinfo=timezone.utc)
    last_run_at = datetime(2026, 4, 30, 8, 0, tzinfo=timezone.utc)
    job_id = uuid.uuid4()
    try:
        async with async_session_factory() as session:
            session.add(
                SysCelery(
                    id=job_id,
                    workspace_id=workspace_id,
                    name="daily-report",
                    task_code="report.daily",
                    task="app.tasks.report_daily",
                    cron="0 8 * * *",
                    args_json=["daily"],
                    kwargs_json={"force": True},
                    enabled=True,
                    next_run_at=next_run_at,
                    last_run_at=last_run_at,
                    last_status="SUCCESS",
                    last_error=None,
                    status="Y",
                    remark="nightly run",
                )
            )
            await session.commit()

            persisted = await session.get(SysCelery, job_id)
            assert persisted is not None
            assert persisted.task_code == "report.daily"
            assert persisted.args_json == ["daily"]
            assert persisted.kwargs_json == {"force": True}
            assert persisted.timezone == "Asia/Shanghai"
            assert persisted.enabled is True
            assert persisted.next_run_at == next_run_at
            assert persisted.last_run_at == last_run_at
            assert persisted.last_status == "SUCCESS"
            assert persisted.last_error is None
            assert persisted.version == 0
    finally:
        await _cleanup_workspace(workspace_id)


@pytest.mark.asyncio
async def test_stop_and_start_job() -> None:
    """Stop/start endpoints should toggle ``enabled`` for one job."""

    await _ensure_celery_table_exists()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        _token, workspace_id, headers = await _register_workspace_user(client)
        job = await _create_job(client, workspace_id=workspace_id, headers=headers)
        job_id = job["id"]

        stopped = await client.post(
            f"/workspaces/{workspace_id}/celery-jobs/{job_id}/stop",
            headers=headers,
        )
        assert stopped.status_code == 200, stopped.text
        assert stopped.json()["enabled"] is False

        started = await client.post(
            f"/workspaces/{workspace_id}/celery-jobs/{job_id}/start",
            headers=headers,
        )
        assert started.status_code == 200, started.text
        assert started.json()["enabled"] is True


@pytest.mark.asyncio
async def test_celery_job_crud_endpoints(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cover list/create/patch/delete and verify run-now enqueues one task."""

    await _ensure_celery_table_exists()
    captured: dict[str, str] = {}

    async def _fake_send_task_now(session, *, workspace_id: uuid.UUID, job_id: uuid.UUID) -> str:
        """Capture run-now arguments and return one fake celery task id."""

        del session
        captured["workspace_id"] = str(workspace_id)
        captured["job_id"] = str(job_id)
        return "mocked-task-id-001"

    monkeypatch.setattr(celery_schedule_service, "send_task_now", _fake_send_task_now)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        _token, workspace_id, headers = await _register_workspace_user(client)

        before = await client.get(f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10", headers=headers)
        assert before.status_code == 200, before.text
        assert before.json()["total"] == 0

        created = await _create_job(client, workspace_id=workspace_id, headers=headers)
        job_id = created["id"]
        assert created["task_code"] == "report.daily"
        assert created["args_json"] == ["daily"]
        assert created["kwargs_json"] == {"force": True}

        listed = await client.get(f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10", headers=headers)
        assert listed.status_code == 200, listed.text
        listed_body = listed.json()
        assert listed_body["total"] == 1
        assert listed_body["items"][0]["id"] == job_id

        patched = await client.patch(
            f"/workspaces/{workspace_id}/celery-jobs/{job_id}",
            headers=headers,
            json={"cron": "*/5 * * * *", "remark": "updated"},
        )
        assert patched.status_code == 200, patched.text
        assert patched.json()["cron"] == "*/5 * * * *"
        assert patched.json()["remark"] == "updated"

        run_now = await client.post(
            f"/workspaces/{workspace_id}/celery-jobs/{job_id}/run-now",
            headers=headers,
        )
        assert run_now.status_code == 200, run_now.text
        assert run_now.json()["accepted"] is True
        assert run_now.json()["task_id"] == "mocked-task-id-001"
        assert run_now.json()["job_id"] == job_id
        assert captured["workspace_id"] == workspace_id
        assert captured["job_id"] == job_id

        deleted = await client.delete(
            f"/workspaces/{workspace_id}/celery-jobs/{job_id}",
            headers=headers,
        )
        assert deleted.status_code == 204, deleted.text

        after = await client.get(f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10", headers=headers)
        assert after.status_code == 200, after.text
        assert after.json()["total"] == 0


@pytest.mark.asyncio
async def test_list_celery_jobs_supports_filter_params() -> None:
    """List endpoint should honor name/task_code/task/enabled filter parameters."""

    await _ensure_celery_table_exists()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        _token, workspace_id, headers = await _register_workspace_user(client)
        _ = await _create_job(client, workspace_id=workspace_id, headers=headers)

        disabled = await client.get(
            f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10&enabled=false",
            headers=headers,
        )
        assert disabled.status_code == 200, disabled.text
        assert disabled.json()["total"] == 0

        exact_task_code = await client.get(
            f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10&task_code=report.daily",
            headers=headers,
        )
        assert exact_task_code.status_code == 200, exact_task_code.text
        assert exact_task_code.json()["total"] == 1

        exact_task = await client.get(
            f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10&task=app.tasks.report_daily",
            headers=headers,
        )
        assert exact_task.status_code == 200, exact_task.text
        assert exact_task.json()["total"] == 1

        fuzzy_name = await client.get(
            f"/workspaces/{workspace_id}/celery-jobs?page=1&page_size=10&name=nightly",
            headers=headers,
        )
        assert fuzzy_name.status_code == 200, fuzzy_name.text
        assert fuzzy_name.json()["total"] == 1


@pytest.mark.asyncio
async def test_duplicate_task_code_returns_conflict_error() -> None:
    """Creating duplicated ``task_code`` in same workspace should return 409 domain error."""

    await _ensure_celery_table_exists()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        _token, workspace_id, headers = await _register_workspace_user(client)

        _ = await _create_job(client, workspace_id=workspace_id, headers=headers)
        duplicated = await client.post(
            f"/workspaces/{workspace_id}/celery-jobs",
            headers=headers,
            json={
                "name": "another-report",
                "task_code": "report.daily",
                "task": "app.tasks.report_daily_v2",
                "cron": "0 9 * * *",
                "enabled": True,
            },
        )
        assert duplicated.status_code != 500, duplicated.text
        assert duplicated.status_code == 409, duplicated.text
        body = duplicated.json()
        assert body["code"] == "celery_job.task_code_conflict"
        assert "task_code" in body["message"]


@pytest.mark.asyncio
async def test_create_job_rejects_non_object_kwargs_json() -> None:
    """Create endpoint should reject ``kwargs_json`` payloads that are not objects."""

    await _ensure_celery_table_exists()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        _token, workspace_id, headers = await _register_workspace_user(client)
        invalid = await client.post(
            f"/workspaces/{workspace_id}/celery-jobs",
            headers=headers,
            json={
                "name": "invalid-kwargs-job",
                "task_code": "invalid.kwargs.job",
                "task": "app.tasks.invalid_kwargs",
                "kwargs_json": ["invalid", "list"],
                "enabled": True,
            },
        )
        assert invalid.status_code == 422, invalid.text
        body = invalid.json()
        assert body["code"] == "request.validation"


@pytest.mark.asyncio
async def test_run_now_returns_stable_error_when_enqueue_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    """Run-now should map enqueue exceptions to stable service unavailable errors."""

    await _ensure_celery_table_exists()

    class _FailingCelery:
        """Fake celery app whose enqueue always fails."""

        def send_task(self, *args, **kwargs):
            """Raise connection error to mimic unavailable broker."""

            del args, kwargs
            raise ConnectionError("broker down")

    monkeypatch.setattr(celery_runtime, "celery_app", _FailingCelery())

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        _token, workspace_id, headers = await _register_workspace_user(client)
        created = await _create_job(client, workspace_id=workspace_id, headers=headers)
        job_id = created["id"]
        run_now = await client.post(
            f"/workspaces/{workspace_id}/celery-jobs/{job_id}/run-now",
            headers=headers,
        )
        assert run_now.status_code == 503, run_now.text
        body = run_now.json()
        assert body["code"] == "celery.enqueue_unavailable"
