"""FastAPI routes for agent v2 (LangGraph + SSE v2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.api.v2.schemas import (
    AgentCapabilityItemOut,
    AgentCapabilityListOut,
    AgentMessageOut,
    AgentRunCreateV2,
    AgentSessionCreateIn,
    AgentSessionDetailOut,
    AgentSessionListItemOut,
    AgentSessionListOut,
    AgentSessionOut,
)
from app.agent.infrastructure.repository import RECENT_AGENT_SESSIONS_DEFAULT_LIMIT
from app.agent.infrastructure import repository as agent_repo
from app.agent.service.agent_graph_run_service import (
    AgentGraphRunService,
    get_agent_graph_run_service,
)
from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.exceptions import AppError

router = APIRouter(prefix="/workspaces/{workspace_id}/agent/v2", tags=["agent-v2"])

_CAPABILITIES: list[AgentCapabilityItemOut] = [
    AgentCapabilityItemOut(id="general", description="通用对话与汇总"),
    AgentCapabilityItemOut(id="file", description="工作区沙箱文件与目录操作"),
    AgentCapabilityItemOut(id="datetime", description="查询服务器当前日期时间"),
]


@router.get("/capabilities", response_model=AgentCapabilityListOut)
async def list_agent_capabilities(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> AgentCapabilityListOut:
    """返回内置能力列表（供前端偏好选择）。"""

    return AgentCapabilityListOut(capabilities=_CAPABILITIES)


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
        updated_at=row.updated_at,
    )


@router.get("/sessions", response_model=AgentSessionListOut)
async def list_agent_sessions(
    workspace_id: uuid.UUID,
    limit: int = Query(default=RECENT_AGENT_SESSIONS_DEFAULT_LIMIT, ge=1, le=50),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> AgentSessionListOut:
    """列出工作区最近的智能体会话。"""

    rows = await agent_repo.list_agent_sessions_recent(
        db, workspace_id=workspace_id, limit=limit
    )
    return AgentSessionListOut(
        sessions=[
            AgentSessionListItemOut(
                id=row.id,
                title=row.title,
                preview=(preview[:120] if preview else None),
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
            for row, preview in rows
        ]
    )


@router.get("/sessions/{session_id}", response_model=AgentSessionDetailOut)
async def get_agent_session_detail(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> AgentSessionDetailOut:
    """加载会话及其消息历史。"""

    row = await agent_repo.get_agent_session(
        db, workspace_id=workspace_id, session_id=session_id
    )
    if row is None:
        raise AppError("agent.session_not_found", "会话不存在或不属于当前工作区。")
    msg_rows = await agent_repo.list_agent_messages_ordered(db, session_id=session_id)
    return AgentSessionDetailOut(
        session=AgentSessionOut(
            id=row.id,
            workspace_id=row.workspace_id,
            title=row.title,
            agent_key=row.agent_key,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
        ),
        messages=[
            AgentMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                seq=m.seq,
                created_at=m.created_at,
            )
            for m in msg_rows
        ],
    )


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_agent_session(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """删除会话及其关联数据。"""

    deleted = await agent_repo.delete_agent_session(
        db, workspace_id=workspace_id, session_id=session_id
    )
    if not deleted:
        raise AppError("agent.session_not_found", "会话不存在或不属于当前工作区。")
    await db.commit()
    return Response(status_code=204)


@router.post("/sessions/{session_id}/runs")
async def create_agent_run_sse(
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    body: AgentRunCreateV2,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    svc: AgentGraphRunService = Depends(get_agent_graph_run_service),
) -> StreamingResponse:
    """发起一次 run，返回 SSE v2 事件流。"""

    run_id = uuid.uuid4()

    async def event_stream():
        try:
            async for chunk in svc.run_stream_sse(
                db,
                run_id=run_id,
                workspace_id=workspace_id,
                user_id=user.id,
                session_id=session_id,
                user_message=body.user_message,
                model_id=body.model_id,
                temperature=body.temperature,
                max_tokens=body.max_tokens,
                preferred_capabilities=body.preferred_capabilities,
            ):
                yield chunk
        except Exception:
            await db.rollback()
            raise

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Minerva-Run-Id": str(run_id),
        },
    )
