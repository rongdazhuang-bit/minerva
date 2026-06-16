"""Async repository helpers for agent sessions, messages, runs, and run nodes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, delete, desc, func, or_, select, text, update
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import (
    AgentLongTermMemory,
    AgentMemoryProfile,
    AgentMessage,
    AgentPlan,
    AgentRun,
    AgentRunNode,
    AgentSession,
)
from app.exceptions import AppError
from app.agent.infrastructure.openai_usage import merge_usage_document

RECENT_AGENT_SESSIONS_DEFAULT_LIMIT: int = 20
AGENT_SESSION_DELETE_LOCK_TIMEOUT_MS: int = 5000


def _is_db_lock_timeout(exc: BaseException) -> bool:
    """Return True when PostgreSQL aborted a statement due to lock wait timeout."""

    if isinstance(exc, DBAPIError):
        orig = getattr(exc, "orig", None)
        if orig is not None and type(orig).__name__ in {
            "LockNotAvailableError",
            "QueryCanceledError",
        }:
            return True
    lowered = str(exc).lower()
    return "lock timeout" in lowered or "locknotavailable" in lowered


async def _set_local_lock_timeout(session: AsyncSession, *, timeout_ms: int) -> None:
    """Apply a per-transaction lock wait cap for session delete."""

    await session.execute(text(f"SET LOCAL lock_timeout = '{timeout_ms}ms'"))


async def cancel_running_agent_runs_for_session(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
) -> int:
    """Mark in-flight runs as cancelled so delete does not wait on stale ``running`` rows."""

    now = datetime.now(timezone.utc)
    res = await session.execute(
        update(AgentRun)
        .where(
            AgentRun.session_id == session_id,
            AgentRun.workspace_id == workspace_id,
            AgentRun.status == "running",
        )
        .values(status="cancelled", finished_at=now)
    )
    await session.flush()
    return int(res.rowcount or 0)


def encode_agent_session_cursor(updated_at: datetime, session_id: uuid.UUID) -> str:
    """Encode ``(updated_at, id)`` for keyset pagination (newest-first list)."""

    ts = updated_at if updated_at.tzinfo else updated_at.replace(tzinfo=timezone.utc)
    return f"{ts.isoformat()}|{session_id}"


def decode_agent_session_cursor(raw: str) -> tuple[datetime, uuid.UUID]:
    """Decode a cursor produced by ``encode_agent_session_cursor``."""

    marker = raw.rfind("|")
    if marker <= 0:
        raise ValueError("invalid agent session cursor")
    ts = datetime.fromisoformat(raw[:marker])
    sid = uuid.UUID(raw[marker + 1 :])
    return ts, sid


async def get_agent_session(
    session: AsyncSession, *, workspace_id: uuid.UUID, session_id: uuid.UUID
) -> AgentSession | None:
    """按主键与工作区加载会话；不匹配时返回 ``None``。"""

    stmt = select(AgentSession).where(
        AgentSession.id == session_id,
        AgentSession.workspace_id == workspace_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_agent_session(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
) -> bool:
    """删除会话及其 message / run / plan / run_node / 画像 / 会话级长期记忆（应用层级联）。"""

    row = await get_agent_session(
        session, workspace_id=workspace_id, session_id=session_id
    )
    if row is None:
        return False

    try:
        await _set_local_lock_timeout(
            session, timeout_ms=AGENT_SESSION_DELETE_LOCK_TIMEOUT_MS
        )
        await cancel_running_agent_runs_for_session(
            session, workspace_id=workspace_id, session_id=session_id
        )

        run_ids = list(
            (
                await session.execute(
                    select(AgentRun.id).where(
                        AgentRun.session_id == session_id,
                        AgentRun.workspace_id == workspace_id,
                    )
                )
            ).scalars().all()
        )

        if run_ids:
            await session.execute(
                delete(AgentRunNode).where(AgentRunNode.run_id.in_(run_ids))
            )
            await session.execute(delete(AgentPlan).where(AgentPlan.run_id.in_(run_ids)))
            await session.execute(
                update(AgentLongTermMemory)
                .where(AgentLongTermMemory.source_run_id.in_(run_ids))
                .values(source_run_id=None)
            )

        await session.execute(
            delete(AgentMessage).where(AgentMessage.session_id == session_id)
        )
        await session.execute(
            delete(AgentLongTermMemory).where(
                AgentLongTermMemory.session_id == session_id,
                AgentLongTermMemory.workspace_id == workspace_id,
            )
        )
        await session.execute(
            delete(AgentMemoryProfile).where(
                AgentMemoryProfile.session_id == session_id,
                AgentMemoryProfile.workspace_id == workspace_id,
            )
        )
        await session.execute(
            delete(AgentRun).where(
                AgentRun.session_id == session_id,
                AgentRun.workspace_id == workspace_id,
            )
        )
        await session.delete(row)
        await session.flush()
    except DBAPIError as exc:
        if _is_db_lock_timeout(exc):
            raise AppError(
                "agent.session_busy",
                "会话正在生成回复或被占用，请稍后再试。",
                409,
            ) from exc
        raise
    return True


def _title_from_first_user_message(content: str) -> str:
    """Derive a single-line session title from the first user question."""

    line = " ".join(content.strip().split())
    return line[:200] if line else ""


async def touch_agent_session(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    title_hint: str | None = None,
) -> None:
    """Bump ``updated_at`` and set title from the first user message when still unset."""

    row = await session.get(AgentSession, session_id)
    if row is None:
        return
    row.updated_at = datetime.now(timezone.utc)
    if title_hint and not (row.title or "").strip():
        derived = _title_from_first_user_message(title_hint)
        if derived:
            row.title = derived
    await session.flush()


async def list_agent_sessions_recent(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int = RECENT_AGENT_SESSIONS_DEFAULT_LIMIT,
    cursor_updated_at: datetime | None = None,
    cursor_id: uuid.UUID | None = None,
) -> tuple[list[tuple[AgentSession, str | None]], bool]:
    """Return recent sessions with preview text and whether a further page exists."""

    cap = max(1, min(limit, 50))
    sort_ts = func.coalesce(AgentSession.updated_at, AgentSession.created_at)
    preview_subq = (
        select(AgentMessage.content)
        .where(
            AgentMessage.session_id == AgentSession.id,
            AgentMessage.role == "user",
        )
        .order_by(AgentMessage.seq.desc())
        .limit(1)
        .correlate(AgentSession)
        .scalar_subquery()
    )
    stmt = select(AgentSession, preview_subq.label("preview")).where(
        AgentSession.workspace_id == workspace_id
    )
    if cursor_updated_at is not None and cursor_id is not None:
        stmt = stmt.where(
            or_(
                sort_ts < cursor_updated_at,
                and_(sort_ts == cursor_updated_at, AgentSession.id < cursor_id),
            )
        )
    stmt = stmt.order_by(desc(sort_ts), desc(AgentSession.id)).limit(cap + 1)
    rows = await session.execute(stmt)
    items = [(row[0], row[1]) for row in rows.all()]
    has_more = len(items) > cap
    return items[:cap], has_more


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

    stored_title: str | None = None
    if title and title.strip():
        derived = _title_from_first_user_message(title)
        if derived:
            stored_title = derived

    row = AgentSession(
        workspace_id=workspace_id,
        created_by=created_by,
        title=stored_title,
        agent_key=agent_key,
        meta_json=meta_json,
    )
    session.add(row)
    await session.flush()
    row.updated_at = datetime.now(timezone.utc)
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
    reasoning_text: str | None = None,
    tool_calls_json: dict[str, Any] | list[Any] | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    meta_json: dict[str, Any] | list[Any] | None = None,
    run_id: uuid.UUID | None = None,
) -> AgentMessage:
    """追加一条消息（自动分配 ``seq``）；可选持久化 ``reasoning_text``。"""

    seq = await allocate_next_message_seq(session, session_id=session_id)
    row = AgentMessage(
        session_id=session_id,
        seq=seq,
        role=role,
        content=content,
        reasoning_text=reasoning_text,
        tool_calls_json=tool_calls_json,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        meta_json=meta_json,
        run_id=run_id,
    )
    session.add(row)
    await session.flush()
    if role == "user" and content:
        prior_user_count = (
            await session.execute(
                select(func.count())
                .select_from(AgentMessage)
                .where(
                    AgentMessage.session_id == session_id,
                    AgentMessage.role == "user",
                )
            )
        ).scalar_one()
        if int(prior_user_count) == 1:
            await touch_agent_session(session, session_id=session_id, title_hint=content)
        else:
            await touch_agent_session(session, session_id=session_id)
    else:
        await touch_agent_session(session, session_id=session_id)
    return row


async def get_agent_message_for_session(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
    message_id: uuid.UUID,
) -> AgentMessage | None:
    """按消息 id 加载会话内一条记录（校验工作区归属）。"""

    stmt = (
        select(AgentMessage)
        .join(AgentSession, AgentMessage.session_id == AgentSession.id)
        .where(
            AgentMessage.id == message_id,
            AgentMessage.session_id == session_id,
            AgentSession.workspace_id == workspace_id,
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def delete_agent_messages_from_seq(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    from_seq: int,
) -> int:
    """删除 ``seq >= from_seq`` 的会话消息（用于重新生成截断）。"""

    stmt = delete(AgentMessage).where(
        AgentMessage.session_id == session_id,
        AgentMessage.seq >= from_seq,
    )
    res = await session.execute(stmt)
    await session.flush()
    return int(res.rowcount or 0)


async def find_last_assistant_message(
    session: AsyncSession, *, session_id: uuid.UUID
) -> AgentMessage | None:
    """返回会话内 ``seq`` 最大的助手消息。"""

    stmt = (
        select(AgentMessage)
        .where(
            AgentMessage.session_id == session_id,
            AgentMessage.role == "assistant",
        )
        .order_by(AgentMessage.seq.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


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
    usage_json: dict[str, Any] | list[Any] | None = None,
    reasoning_text: str | None = None,
) -> AgentRunNode:
    """插入一条运行节点记录；可选持久化 ``reasoning_text``。"""

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
        usage_json=usage_json,
        reasoning_text=reasoning_text,
    )
    session.add(row)
    await session.flush()
    return row


async def update_run_node_usage(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    usage_json: dict[str, Any] | list[Any],
) -> None:
    """Set ``usage_json`` on one ``agent_run_node`` row (rollup of child totals)."""

    row = await session.get(AgentRunNode, node_id)
    if row is None:
        return
    row.usage_json = usage_json
    await session.flush()


async def update_run_node_reasoning_text(
    session: AsyncSession,
    *,
    node_id: uuid.UUID,
    reasoning_text: str | None,
) -> None:
    """Update ``reasoning_text`` on one ``agent_run_node`` row; no-op if the row is missing."""

    row = await session.get(AgentRunNode, node_id)
    if row is None:
        return
    row.reasoning_text = reasoning_text
    await session.flush()


async def merge_run_usage_json(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    delta: dict[str, Any],
) -> None:
    """Merge ``delta`` into ``agent_run.usage_json`` using layered merge rules."""

    row = await session.get(AgentRun, run_id)
    if row is None:
        return
    base = row.usage_json if isinstance(row.usage_json, dict) else {}
    row.usage_json = merge_usage_document(base, delta)
    await session.flush()


async def merge_session_usage_json(
    session: AsyncSession,
    *,
    session_id: uuid.UUID,
    delta: dict[str, Any],
) -> None:
    """Merge run-level usage into ``agent_session.usage_json`` (drops ``by_step``)."""

    row = await session.get(AgentSession, session_id)
    if row is None:
        return
    base = row.usage_json if isinstance(row.usage_json, dict) else {}
    clean_delta = {k: v for k, v in delta.items() if k != "by_step"}
    row.usage_json = merge_usage_document(base, clean_delta)
    await session.flush()


async def patch_assistant_message_usage_by_run(
    session: AsyncSession,
    *,
    run_id: uuid.UUID,
    usage_json: dict[str, Any],
) -> None:
    """Attach ``usage_json`` under ``meta_json.usage`` on the latest assistant row for ``run_id``."""

    stmt = (
        select(AgentMessage)
        .where(AgentMessage.run_id == run_id, AgentMessage.role == "assistant")
        .order_by(AgentMessage.seq.desc())
        .limit(1)
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        return
    meta = dict(row.meta_json) if isinstance(row.meta_json, dict) else {}
    meta["usage"] = usage_json
    row.meta_json = meta
    await session.flush()


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
