"""Async repository helpers for agent sessions, messages, runs, and run nodes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentMessage, AgentRun, AgentRunNode, AgentSession


async def get_agent_session(
    session: AsyncSession, *, workspace_id: uuid.UUID, session_id: uuid.UUID
) -> AgentSession | None:
    """按主键与工作区加载会话；不匹配时返回 ``None``。"""

    stmt = select(AgentSession).where(
        AgentSession.id == session_id,
        AgentSession.workspace_id == workspace_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_agent_session(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    created_by: uuid.UUID | None,
    title: str | None = None,
    agent_key: str | None = None,
    meta_json: dict[str, Any] | list[Any] | None = None,
) -> AgentSession:
    """插入一条会话记录并 ``flush`` 以便获得主键。"""

    row = AgentSession(
        workspace_id=workspace_id,
        created_by=created_by,
        title=title,
        agent_key=agent_key,
        meta_json=meta_json,
    )
    session.add(row)
    await session.flush()
    return row


async def create_agent_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    session_id: uuid.UUID,
    workspace_id: uuid.UUID,
    triggered_by: uuid.UUID | None,
    model: str,
    provider_kind: str | None,
    request_meta_json: dict[str, Any] | list[Any] | None = None,
) -> AgentRun:
    """插入一条 run（``id`` 即对外 ``run_id``），初始状态为 ``running``。"""

    now = datetime.now(timezone.utc)
    row = AgentRun(
        id=run_id,
        session_id=session_id,
        workspace_id=workspace_id,
        triggered_by=triggered_by,
        model=model,
        provider_kind=provider_kind,
        started_at=now,
        request_meta_json=request_meta_json,
    )
    session.add(row)
    await session.flush()
    return row


async def allocate_next_message_seq(session: AsyncSession, *, session_id: uuid.UUID) -> int:
    """在锁定会话行后分配下一条 ``agent_message.seq``，避免并发重复。"""

    lock_stmt = select(AgentSession.id).where(AgentSession.id == session_id).with_for_update()
    res = await session.execute(lock_stmt)
    if res.scalar_one_or_none() is None:
        raise ValueError("agent session not found")
    max_stmt = select(func.coalesce(func.max(AgentMessage.seq), 0)).where(AgentMessage.session_id == session_id)
    cur = (await session.execute(max_stmt)).scalar_one()
    return int(cur) + 1


async def append_agent_message(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    role: str,
    content: str | None = None,
    tool_calls_json: dict[str, Any] | list[Any] | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    meta_json: dict[str, Any] | list[Any] | None = None,
    run_id: uuid.UUID | None = None,
) -> AgentMessage:
    """追加一条消息（自动分配 ``seq``）。"""

    seq = await allocate_next_message_seq(session, session_id=session_id)
    row = AgentMessage(
        session_id=session_id,
        seq=seq,
        role=role,
        content=content,
        tool_calls_json=tool_calls_json,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        meta_json=meta_json,
        run_id=run_id,
    )
    session.add(row)
    await session.flush()
    return row


async def list_agent_messages_ordered(
    session: AsyncSession, *, session_id: uuid.UUID
) -> list[AgentMessage]:
    """按 ``seq`` 升序返回会话内全部消息。"""

    stmt = (
        select(AgentMessage)
        .where(AgentMessage.session_id == session_id)
        .order_by(AgentMessage.seq.asc())
    )
    r = await session.execute(stmt)
    return list(r.scalars().all())


async def insert_run_node(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    run_id: uuid.UUID,
    parent_node_id: uuid.UUID | None,
    sequence_idx: int,
    node_type: str,
    node_name: str,
    status: str = "pending",
    inputs_json: dict[str, Any] | list[Any] | None = None,
    outputs_json: dict[str, Any] | list[Any] | None = None,
    meta_json: dict[str, Any] | list[Any] | None = None,
) -> AgentRunNode:
    """插入一条运行节点记录。"""

    row = AgentRunNode(
        id=node_id,
        run_id=run_id,
        parent_node_id=parent_node_id,
        sequence_idx=sequence_idx,
        node_type=node_type,
        node_name=node_name,
        status=status,
        inputs_json=inputs_json,
        outputs_json=outputs_json,
        meta_json=meta_json,
    )
    session.add(row)
    await session.flush()
    return row


async def finalize_agent_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    status: str,
    error_code: str | None = None,
    error_message: str | None = None,
    usage_json: dict[str, Any] | list[Any] | None = None,
) -> None:
    """结束 run：写状态、结束时间与可选错误/用量。"""

    row = await session.get(AgentRun, run_id)
    if row is None:
        return
    row.status = status
    row.finished_at = datetime.now(timezone.utc)
    row.error_code = error_code
    row.error_message = error_message
    if usage_json is not None:
        row.usage_json = usage_json
    await session.flush()
