"""FastAPI routes for agent sessions and streaming runs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.api.schemas import AgentRunCreateIn, AgentSessionCreateIn, AgentSessionOut
from app.agent.infrastructure import repository as agent_repo
from app.agent.service.agent_run_service import AgentRunService, get_agent_run_service
from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db

router = APIRouter(prefix="/workspaces/{workspace_id}/agent", tags=["agent"])


@router.post("/sessions", response_model=AgentSessionOut)
async def create_agent_session(
    workspace_id: uuid.UUID,
    body: AgentSessionCreateIn,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSessionOut:
    """创建智能体会话。"""

    row = await agent_repo.create_agent_session(
        db,
        workspace_id=workspace_id,
        created_by=user.id,
        title=body.title,
        agent_key=body.agent_key,
        meta_json=None,
    )
    await db.commit()
    await db.refresh(row)
    return AgentSessionOut(
        id=row.id,
        workspace_id=row.workspace_id,
        title=row.title,
        agent_key=row.agent_key,
        status=row.status,
        created_at=row.created_at,
    )


@router.post("/sessions/{session_id}/runs")
async def create_agent_run_sse(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    body: AgentRunCreateIn,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    svc: AgentRunService = Depends(get_agent_run_service),
) -> StreamingResponse:
    """发起一次 run，默认返回 SSE 事件流。"""

    async def event_stream():
        try:
            async for chunk in svc.run_stream_sse(
                db,
                workspace_id=workspace_id,
                user_id=user.id,
                session_id=session_id,
                user_message=body.user_message,
                skill_ids=body.skill_ids,
                provider_kind=body.provider_kind,
                base_url=body.base_url,
                api_key=body.api_key,
                model=body.model,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
            ):
                yield chunk
            await db.commit()
        except Exception:
            await db.rollback()
            raise

    return StreamingResponse(event_stream(), media_type="text/event-stream")
