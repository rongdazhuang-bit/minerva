"""FastAPI routes for agent v2 (LangGraph + SSE v2)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.api.v2.schemas import (
    AgentConversationModelOut,
    AgentOverviewUsageDailyStatsOut,
    AgentSkillItemOut,
    AgentSkillListOut,
    AgentMessageOut,
    AgentMessageReasoningOut,
    AgentRunCreateV2,
    AgentSessionCreateIn,
    AgentSessionDetailOut,
    AgentSessionListItemOut,
    AgentSessionListOut,
    AgentSessionOut,
)
from app.agent.infrastructure.repository import (
    RECENT_AGENT_SESSIONS_DEFAULT_LIMIT,
    decode_agent_session_cursor,
    encode_agent_session_cursor,
)
from app.agent.infrastructure import repository as agent_repo
from app.agent.infrastructure.skill_loader import list_indexed_skills
from app.agent.api.v2.skills_mgmt_router import router as skills_mgmt_router
from app.agent.service.agent_graph_run_service import (
    AgentGraphRunService,
    get_agent_graph_run_service,
)
from app.agent.service.overview_usage_daily_stats import compute_overview_usage_daily_stats
from app.core.api.deps import get_current_user, require_workspace_member
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.exceptions import AppError
from app.sys.model_provider.infrastructure import repository as model_repo

router = APIRouter(prefix="/workspaces/{workspace_id}/agent/v2", tags=["agent-v2"])

router.include_router(skills_mgmt_router)


def _to_agent_conversation_model(row) -> AgentConversationModelOut:
    """Map a filtered SysModel row to the agent conversation picker payload."""

    endpoint = (row.endpoint_url or "").strip()
    return AgentConversationModelOut(
        id=row.id,
        provider_name=row.provider_name,
        model_name=row.model_name,
        endpoint_url=endpoint,
        max_tokens=row.max_tokens,
        tags=list(row.tags or []),
    )


@router.get("/models", response_model=list[AgentConversationModelOut])
async def list_agent_conversation_models(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> list[AgentConversationModelOut]:
    """返回当前工作区可用于 Agent 对话的模型（SQL 已过滤）。"""

    rows = await model_repo.list_agent_conversation_models(db, workspace_id=workspace_id)
    return [_to_agent_conversation_model(r) for r in rows]


@router.get("/skills", response_model=AgentSkillListOut)
async def list_agent_skills(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
) -> AgentSkillListOut:
    """返回内置技能列表（来自 ``skills/INDEX.md``，供前端偏好选择）。"""

    return AgentSkillListOut(
        skills=[
            AgentSkillItemOut(id=s.id, description=s.description)
            for s in list_indexed_skills()
        ]
    )


@router.get("/overview-usage-daily-stats", response_model=AgentOverviewUsageDailyStatsOut)
async def get_agent_overview_usage_daily_stats(
    workspace_id: uuid.UUID,
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> AgentOverviewUsageDailyStatsOut:
    """Return last 7 local days of agent token usage grouped by token type."""

    return await compute_overview_usage_daily_stats(db, workspace_id)


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
    cursor: str | None = Query(default=None, description="Keyset cursor from prior page ``next_cursor``."),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    db: AsyncSession = Depends(get_db),
) -> AgentSessionListOut:
    """列出工作区最近的智能体会话（支持 ``cursor`` 滚动分页）。"""

    cursor_updated_at = None
    cursor_id = None
    if cursor:
        try:
            cursor_updated_at, cursor_id = decode_agent_session_cursor(cursor)
        except ValueError as e:
            raise AppError("agent.invalid_session_cursor", "会话列表游标无效。") from e

    rows, has_more = await agent_repo.list_agent_sessions_recent(
        db,
        workspace_id=workspace_id,
        limit=limit,
        cursor_updated_at=cursor_updated_at,
        cursor_id=cursor_id,
    )
    next_cursor: str | None = None
    if has_more and rows:
        last_row, _preview = rows[-1]
        ts = last_row.updated_at or last_row.created_at
        next_cursor = encode_agent_session_cursor(ts, last_row.id)
    return AgentSessionListOut(
        sessions=[
            AgentSessionListItemOut(
                id=row.id,
                title=row.title,
                preview=(preview[:120] if preview else None),
                created_at=row.created_at,
                updated_at=row.updated_at,
                usage=row.usage_json if isinstance(row.usage_json, dict) else None,
            )
            for row, preview in rows
        ],
        has_more=has_more,
        next_cursor=next_cursor,
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
    message_outs: list[AgentMessageOut] = []
    for m in msg_rows:
        reasoning_raw = (
            m.meta_json.get("reasoning")
            if isinstance(m.meta_json, dict)
            else None
        )
        reasoning: AgentMessageReasoningOut | None = None
        if isinstance(reasoning_raw, dict):
            try:
                reasoning = AgentMessageReasoningOut.model_validate(reasoning_raw)
            except Exception:
                reasoning = None
        message_outs.append(
            AgentMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                seq=m.seq,
                created_at=m.created_at,
                meta_json=m.meta_json if isinstance(m.meta_json, dict) else None,
                reasoning_text=m.reasoning_text,
                reasoning=reasoning,
            )
        )
    return AgentSessionDetailOut(
        session=AgentSessionOut(
            id=row.id,
            workspace_id=row.workspace_id,
            title=row.title,
            agent_key=row.agent_key,
            status=row.status,
            created_at=row.created_at,
            updated_at=row.updated_at,
            usage=row.usage_json if isinstance(row.usage_json, dict) else None,
        ),
        messages=message_outs,
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
                preferred_skills=body.preferred_skills,
                regenerate_from_message_id=body.regenerate_from_message_id,
                regenerate_last_assistant=body.regenerate_last_assistant,
                enable_thinking=body.enable_thinking,
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
