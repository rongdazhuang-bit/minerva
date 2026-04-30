"""Workspace-scoped CRUD routes for celery schedule jobs."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_current_user,
    require_workspace_member,
    require_workspace_owner_or_admin,
)
from app.dependencies import get_db
from app.domain.identity.models import User
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.celery.api.schemas import (
    CeleryJobCreateIn,
    CeleryJobDetailOut,
    CeleryJobListItemOut,
    CeleryJobListPageOut,
    CeleryJobPatchIn,
    CeleryJobRunNowOut,
)
from app.sys.celery.domain.db.models import SysCelery
from app.sys.celery.service import celery_schedule_service as svc

router = APIRouter(
    prefix="/workspaces/{workspace_id}/celery-jobs",
    tags=["celery-jobs"],
)


def _to_list_item(row: SysCelery) -> CeleryJobListItemOut:
    """Project ORM row to list response schema."""

    return CeleryJobListItemOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        task_code=row.task_code,
        task=row.task,
        cron=row.cron,
        args_json=row.args_json,
        kwargs_json=row.kwargs_json,
        timezone=row.timezone,
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_status=row.last_status,
        last_error=row.last_error,
        version=row.version,
        status=row.status,
        remark=row.remark,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_detail(row: SysCelery) -> CeleryJobDetailOut:
    """Project ORM row to detail response schema."""

    return CeleryJobDetailOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        task_code=row.task_code,
        task=row.task,
        cron=row.cron,
        args_json=row.args_json,
        kwargs_json=row.kwargs_json,
        timezone=row.timezone,
        enabled=row.enabled,
        next_run_at=row.next_run_at,
        last_run_at=row.last_run_at,
        last_status=row.last_status,
        last_error=row.last_error,
        version=row.version,
        status=row.status,
        remark=row.remark,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_create_data(body: CeleryJobCreateIn) -> dict[str, Any]:
    """Convert create schema to service payload dictionary."""

    return {
        "name": body.name.strip(),
        "task_code": body.task_code.strip(),
        "task": body.task.strip(),
        "cron": body.cron.strip() if body.cron else None,
        "args_json": body.args_json,
        "kwargs_json": body.kwargs_json,
        "timezone": body.timezone.strip() if body.timezone else None,
        "enabled": body.enabled,
        "status": body.status.strip() if body.status else None,
        "remark": body.remark.strip() if body.remark else None,
    }


def _to_patch_data(body: CeleryJobPatchIn) -> dict[str, Any]:
    """Convert patch schema to partial update payload."""

    data = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            patch[key] = value.strip()
            continue
        patch[key] = value
    return patch


@router.get("", response_model=CeleryJobListPageOut)
async def list_celery_jobs(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> CeleryJobListPageOut:
    """Return paginated celery job list under one workspace."""

    rows, total = await svc.list_jobs_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
    )
    return CeleryJobListPageOut(items=[_to_list_item(r) for r in rows], total=total)


@router.post("", response_model=CeleryJobDetailOut, status_code=status.HTTP_201_CREATED)
async def create_celery_job(
    workspace_id: uuid.UUID,
    body: CeleryJobCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> CeleryJobDetailOut:
    """Create one celery job row in workspace scope."""

    row = await svc.create_job(
        session,
        workspace_id=workspace_id,
        data=_to_create_data(body),
    )
    return _to_detail(row)


@router.patch("/{job_id}", response_model=CeleryJobDetailOut)
async def patch_celery_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    body: CeleryJobPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> CeleryJobDetailOut:
    """Patch one celery job and return refreshed detail."""

    patch = _to_patch_data(body)
    if not patch:
        row = await svc.get_job(
            session,
            workspace_id=workspace_id,
            job_id=job_id,
        )
        return _to_detail(row)
    row = await svc.update_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
        patch=patch,
    )
    return _to_detail(row)


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def delete_celery_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    """Delete one celery job row."""

    await svc.delete_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{job_id}/stop", response_model=CeleryJobDetailOut)
async def stop_celery_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> CeleryJobDetailOut:
    """Disable one celery job by setting ``enabled`` to false."""

    row = await svc.stop_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return _to_detail(row)


@router.post("/{job_id}/start", response_model=CeleryJobDetailOut)
async def start_celery_job(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> CeleryJobDetailOut:
    """Enable one celery job by setting ``enabled`` to true."""

    row = await svc.start_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return _to_detail(row)


@router.post(
    "/{job_id}/run-now",
    response_model=CeleryJobRunNowOut,
    status_code=status.HTTP_501_NOT_IMPLEMENTED,
)
async def run_celery_job_now(
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> CeleryJobRunNowOut:
    """Return placeholder run-now response without celery runtime dependency."""

    await svc.get_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
    )
    return CeleryJobRunNowOut(
        accepted=False,
        job_id=job_id,
        reason="run_now_not_implemented_in_task2",
    )
