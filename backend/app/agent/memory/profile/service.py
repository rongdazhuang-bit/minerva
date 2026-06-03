"""Business helpers for persistent memory profiles."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.memory.profile import repository as profile_repo


async def get_profile_layers_text(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    session_id: uuid.UUID | None,
) -> tuple[str, str]:
    """Return (workspace_profile_text, session_profile_text) for planner context."""

    workspace_row = await profile_repo.get_workspace_profile(
        session, workspace_id=workspace_id
    )
    workspace_text = (workspace_row.profile_text if workspace_row else "").strip()
    session_text = ""
    if session_id is not None:
        session_row = await profile_repo.get_session_profile(
            session, workspace_id=workspace_id, session_id=session_id
        )
        session_text = (session_row.profile_text if session_row else "").strip()
    return workspace_text, session_text
