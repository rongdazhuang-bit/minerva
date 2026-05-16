"""FastAPI routes for agent sessions and streaming runs."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.api.schemas import (
    AgentMessageOut,
    AgentRunCreateIn,
    AgentSessionCreateIn,
    AgentSessionDetailOut,
    AgentSessionListItemOut,
    AgentSessionListOut,
    AgentSessionOut,
    AgentSkillItemOut,
    AgentSkillListOut,
)
from app.agent.infrastructure.repository import RECENT_AGENT_SESSIONS_DEFAULT_LIMIT
from app.exceptions import AppError
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure import skill_loader
from app.agent.service.agent_run_service import AgentRunService, get_agent_run_service
from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db

router = APIRouter(prefix="/workspaces/{workspace_id}/agent", tags=["agent"])


@router.get("/skills", response_model=AgentSkillListOut)
async def list_agent_skills(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> AgentSkillListOut:
    """返回 INDEX 中可加载的技能列表（供前端 ``/`` 菜单）。"""

    rows = skill_loader.list_indexed_skills()
    return AgentSkillListOut(
        skills=[AgentSkillItemOut(id=r["id"], description=r["description"]) for r in rows]
    )


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
    """列出工作区最近的智能体会话（侧栏历史）。"""

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
    """加载会话及其消息历史（用于恢复对话）。"""

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
    """删除会话及其关联的 message、run、run_node（数据库级联）。"""

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
    body: AgentRunCreateIn,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    svc: AgentRunService = Depends(get_agent_run_service),
) -> StreamingResponse:
    """发起一次 run，返回 OpenAI 兼容的 ``chat.completion.chunk`` SSE 流。"""

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

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Minerva-Run-Id": str(run_id),
        },
    )
