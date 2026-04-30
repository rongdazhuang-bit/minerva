"""Regression test for persisted sys_celery extended fields."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

import app.domain.identity.models  # noqa: F401
from app.infrastructure.db.session import async_session_factory, engine
from app.sys.celery.domain.db.models import SysCelery


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
                    args_json='["daily"]',
                    kwargs_json='{"force": true}',
                    timezone="Asia/Shanghai",
                    enabled=True,
                    next_run_at=next_run_at,
                    last_run_at=last_run_at,
                    last_status="SUCCESS",
                    last_error=None,
                    version=2,
                    status="Y",
                    remark="nightly run",
                )
            )
            await session.commit()

            persisted = await session.get(SysCelery, job_id)
            assert persisted is not None
            assert persisted.task_code == "report.daily"
            assert persisted.args_json == '["daily"]'
            assert persisted.kwargs_json == '{"force": true}'
            assert persisted.timezone == "Asia/Shanghai"
            assert persisted.enabled is True
            assert persisted.next_run_at == next_run_at
            assert persisted.last_run_at == last_run_at
            assert persisted.last_status == "SUCCESS"
            assert persisted.last_error is None
            assert persisted.version == 2
    finally:
        await _cleanup_workspace(workspace_id)
