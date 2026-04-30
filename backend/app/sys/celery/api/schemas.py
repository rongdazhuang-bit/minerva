"""Pydantic schemas for workspace-scoped celery job APIs."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class CeleryJobCreateIn(BaseModel):
    """Input payload for creating one celery schedule job."""

    name: str = Field(min_length=1, max_length=64)
    task_code: str = Field(min_length=1, max_length=64)
    task: str = Field(min_length=1, max_length=128)
    cron: str | None = Field(default=None, max_length=64)
    args_json: dict[str, Any] | list[Any] | None = None
    kwargs_json: dict[str, Any] | list[Any] | None = None
    timezone: str | None = Field(default="Asia/Shanghai", max_length=64)
    enabled: bool = True
    status: str | None = Field(default=None, max_length=2)
    remark: str | None = Field(default=None, max_length=128)


class CeleryJobPatchIn(BaseModel):
    """Partial payload for patching one celery schedule job."""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    task_code: str | None = Field(default=None, min_length=1, max_length=64)
    task: str | None = Field(default=None, min_length=1, max_length=128)
    cron: str | None = Field(default=None, max_length=64)
    args_json: dict[str, Any] | list[Any] | None = None
    kwargs_json: dict[str, Any] | list[Any] | None = None
    timezone: str | None = Field(default=None, max_length=64)
    enabled: bool | None = None
    status: str | None = Field(default=None, max_length=2)
    remark: str | None = Field(default=None, max_length=128)


class CeleryJobListItemOut(BaseModel):
    """List-row projection for a workspace celery job."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    task_code: str
    task: str
    cron: str | None
    args_json: dict[str, Any] | list[Any] | None
    kwargs_json: dict[str, Any] | list[Any] | None
    timezone: str | None
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    version: int
    status: str | None
    remark: str | None
    create_at: datetime | None
    update_at: datetime | None


class CeleryJobDetailOut(BaseModel):
    """Detail payload for one celery job entry."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    workspace_id: uuid.UUID
    name: str
    task_code: str
    task: str
    cron: str | None
    args_json: dict[str, Any] | list[Any] | None
    kwargs_json: dict[str, Any] | list[Any] | None
    timezone: str | None
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    last_error: str | None
    version: int
    status: str | None
    remark: str | None
    create_at: datetime | None
    update_at: datetime | None


class CeleryJobListPageOut(BaseModel):
    """Paginated list payload for celery jobs."""

    items: list[CeleryJobListItemOut]
    total: int


class CeleryJobRunNowOut(BaseModel):
    """Placeholder response for run-now endpoint in Task2."""

    accepted: bool
    job_id: uuid.UUID
    reason: str
