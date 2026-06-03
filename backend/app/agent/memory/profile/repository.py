"""CRUD for ``agent_memory_profile`` (mem0 backend)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.domain.db.models import AgentMemoryProfile


async def get_workspace_profile(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
) -> AgentMemoryProfile | None:
    """Return workspace-level profile row (``session_id`` IS NULL)."""

    stmt = select(AgentMemoryProfile).where(
        AgentMemoryProfile.workspace_id == workspace_id,
        AgentMemoryProfile.session_id.is_(None),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def get_session_profile(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID,
) -> AgentMemoryProfile | None:
    """Return session-level profile row."""

    stmt = select(AgentMemoryProfile).where(
        AgentMemoryProfile.workspace_id == workspace_id,
        AgentMemoryProfile.session_id == session_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_profiles(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID | None = None,
) -> list[AgentMemoryProfile]:
    """List profiles for a workspace, optionally filtered by session."""

    stmt = select(AgentMemoryProfile).where(
        AgentMemoryProfile.workspace_id == workspace_id,
    )
    if session_id is not None:
        stmt = stmt.where(AgentMemoryProfile.session_id == session_id)
    stmt = stmt.order_by(AgentMemoryProfile.updated_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def upsert_profile(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID | None,
    profile_text: str,
    updated_by: uuid.UUID | None = None,
) -> AgentMemoryProfile:
    """Insert or update a profile row by workspace + session scope."""

    if session_id is None:
        existing = await get_workspace_profile(session, workspace_id=workspace_id)
    else:
        existing = await get_session_profile(
            session, workspace_id=workspace_id, session_id=session_id
        )
    if existing is not None:
        existing.profile_text = profile_text
        existing.updated_by = updated_by
        existing.updated_at = datetime.now(timezone.utc)
        await session.flush()
        return existing
    row = AgentMemoryProfile(
        workspace_id=workspace_id,
        session_id=session_id,
        profile_text=profile_text,
        updated_by=updated_by,
    )
    session.add(row)
    await session.flush()
    return row


async def get_profile_by_id(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> AgentMemoryProfile | None:
    """Load one profile scoped to workspace."""

    row = await session.get(AgentMemoryProfile, profile_id)
    if row is None or row.workspace_id != workspace_id:
        return None
    return row


async def delete_profile(
    session: AsyncSession,
    *,
    profile_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> bool:
    """Delete profile when it belongs to the workspace."""

    row = await get_profile_by_id(
        session, profile_id=profile_id, workspace_id=workspace_id
    )
    if row is None:
        return False
    await session.delete(row)
    await session.flush()
    return True
