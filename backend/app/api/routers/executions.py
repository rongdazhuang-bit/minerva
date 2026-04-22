from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_workspace_member
from app.dependencies import get_db
from app.domain.execution.models import Execution, ExecutionEvent
from app.domain.execution.services import start_execution
from app.exceptions import AppError

router = APIRouter(prefix="/workspaces", tags=["executions"])

ARQ_JOB = "app.worker.tasks.handle_execution_tick"


class StartExecutionIn(BaseModel):
    rule_id: uuid.UUID
    input: dict[str, Any] = Field(default_factory=dict)


class ExecutionListItemOut(BaseModel):
    id: uuid.UUID
    workspace_id: uuid.UUID
    rule_id: uuid.UUID
    rule_version_id: uuid.UUID
    status: str
    step_count: int
    error_code: str | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionEventOut(BaseModel):
    id: uuid.UUID
    event_type: str
    payload: dict[str, Any]
    created_at: datetime

    model_config = {"from_attributes": True}


class ExecutionDetailOut(ExecutionListItemOut):
    current_node_id: str | None
    error_detail: str | None
    input_json: dict[str, Any]
    context_json: dict[str, Any]
    events: list[ExecutionEventOut]


@router.post("/{workspace_id}/executions", response_model=ExecutionListItemOut, status_code=201)
async def create_execution(
    workspace_id: uuid.UUID,
    body: StartExecutionIn,
    request: Request,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
):
    ex = await start_execution(
        session,
        workspace_id=workspace_id,
        rule_id=body.rule_id,
        input_json=body.input,
    )
    await session.commit()
    await session.refresh(ex)
    pool = getattr(request.app.state, "arq_pool", None)
    if pool is not None:
        await pool.enqueue_job(ARQ_JOB, str(ex.id))
    return ex


@router.get("/{workspace_id}/executions", response_model=list[ExecutionListItemOut])
async def list_executions(
    workspace_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> list[Execution]:
    r = await session.execute(
        select(Execution)
        .where(Execution.workspace_id == workspace_id)
        .order_by(Execution.created_at.desc())
    )
    return list(r.scalars().all())


@router.get("/{workspace_id}/executions/{execution_id}", response_model=ExecutionDetailOut)
async def get_execution(
    workspace_id: uuid.UUID,
    execution_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _member: uuid.UUID = Depends(require_workspace_member),
) -> ExecutionDetailOut:
    ex = await session.get(Execution, execution_id)
    if ex is None or ex.workspace_id != workspace_id:
        raise AppError("execution.not_found", "Execution not found", 404)
    ev = await session.execute(
        select(ExecutionEvent)
        .where(ExecutionEvent.execution_id == execution_id)
        .order_by(ExecutionEvent.created_at.asc())
    )
    events = list(ev.scalars().all())
    return ExecutionDetailOut(
        id=ex.id,
        workspace_id=ex.workspace_id,
        rule_id=ex.rule_id,
        rule_version_id=ex.rule_version_id,
        status=ex.status,
        step_count=ex.step_count,
        error_code=ex.error_code,
        created_at=ex.created_at,
        current_node_id=ex.current_node_id,
        error_detail=ex.error_detail,
        input_json=ex.input_json,
        context_json=ex.context_json,
        events=[
            ExecutionEventOut(
                id=e.id, event_type=e.event_type, payload=e.payload, created_at=e.created_at
            )
            for e in events
        ],
    )
