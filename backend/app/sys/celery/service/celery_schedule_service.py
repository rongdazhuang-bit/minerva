"""Business logic for workspace-level celery schedule job management."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import enqueue_task
from app.exceptions import AppError
from app.sys.celery.domain.db.models import SysCelery
from app.sys.celery.infrastructure import repository as repo


_TASK_CODE_UNIQUE_CONSTRAINT = "uq_sys_celery_workspace_task_code"


def _utc_now() -> datetime:
    """Return UTC timestamp used by audit fields."""

    return datetime.now(UTC)


def _normalize_nullable_str(value: str | None) -> str | None:
    """Trim nullable text and coerce blank values to ``None``."""

    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def _normalize_required_str(value: str) -> str:
    """Trim required text fields and reject blank values."""

    trimmed = value.strip()
    if not trimmed:
        raise AppError("celery_job.invalid_argument", "Required string field cannot be blank", 422)
    return trimmed


def _translate_integrity_error(exc: IntegrityError) -> AppError:
    """Map DB integrity violations to stable domain errors."""

    raw = str(getattr(exc, "orig", exc))
    if _TASK_CODE_UNIQUE_CONSTRAINT in raw or "sys_celery_workspace_task_code" in raw:
        return AppError(
            "celery_job.task_code_conflict",
            "task_code already exists in this workspace",
            409,
        )
    return AppError("celery_job.integrity_error", "Invalid celery job data", 409)


def _normalize_task_args(value: Any) -> list[Any]:
    """Convert persisted ``args_json`` payload to Celery positional args."""

    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_task_kwargs(value: Any) -> dict[str, Any]:
    """Convert persisted ``kwargs_json`` payload to Celery keyword args."""

    if isinstance(value, dict):
        return value
    return {}


async def list_jobs_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    page: int,
    page_size: int,
) -> tuple[list[SysCelery], int]:
    """Return one paginated job list page and total count."""

    total = await repo.count_for_workspace(session, workspace_id=workspace_id)
    offset = (page - 1) * page_size
    rows = await repo.list_for_workspace_page(
        session,
        workspace_id=workspace_id,
        limit=page_size,
        offset=offset,
    )
    return list(rows), total


async def get_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> SysCelery:
    """Load one job row or raise a 404 domain error."""

    row = await repo.get_for_workspace(session, workspace_id=workspace_id, job_id=job_id)
    if row is None:
        raise AppError("celery_job.not_found", "Celery job not found", 404)
    return row


async def create_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    data: dict[str, Any],
) -> SysCelery:
    """Create one workspace celery job and persist it."""

    now = _utc_now()
    row = SysCelery(
        workspace_id=workspace_id,
        name=_normalize_required_str(str(data["name"])),
        task_code=_normalize_required_str(str(data["task_code"])),
        task=_normalize_required_str(str(data["task"])),
        cron=_normalize_nullable_str(data.get("cron")),
        args_json=data.get("args_json"),
        kwargs_json=data.get("kwargs_json"),
        timezone=_normalize_nullable_str(data.get("timezone")) or "Asia/Shanghai",
        enabled=bool(data.get("enabled", True)),
        status=_normalize_nullable_str(data.get("status")),
        remark=_normalize_nullable_str(data.get("remark")),
        create_at=now,
        update_at=now,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _translate_integrity_error(exc) from exc
    await session.refresh(row)
    return row


async def update_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysCelery:
    """Patch one job under workspace scope and persist changes."""

    row = await get_job(session, workspace_id=workspace_id, job_id=job_id)
    for key, value in patch.items():
        if key in {"name", "task_code", "task"} and isinstance(value, str):
            setattr(row, key, _normalize_required_str(value))
            continue
        if key in {"cron", "timezone", "status", "remark"}:
            setattr(row, key, _normalize_nullable_str(value))
            continue
        setattr(row, key, value)
    row.update_at = _utc_now()
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise _translate_integrity_error(exc) from exc
    await session.refresh(row)
    return row


async def delete_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> None:
    """Delete one workspace job row physically."""

    row = await get_job(session, workspace_id=workspace_id, job_id=job_id)
    await session.delete(row)
    await session.commit()


async def stop_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> SysCelery:
    """Disable one job by setting ``enabled=False``."""

    return await update_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
        patch={"enabled": False},
    )


async def start_job(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> SysCelery:
    """Enable one job by setting ``enabled=True``."""

    return await update_job(
        session,
        workspace_id=workspace_id,
        job_id=job_id,
        patch={"enabled": True},
    )


async def send_task_now(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    job_id: uuid.UUID,
) -> str:
    """Enqueue one existing job immediately and return accepted task id."""

    row = await get_job(session, workspace_id=workspace_id, job_id=job_id)
    task_id = enqueue_task(
        row.task,
        args=_normalize_task_args(row.args_json),
        kwargs=_normalize_task_kwargs(row.kwargs_json),
    )
    return task_id
