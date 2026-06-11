"""Route-level dependencies for workspace user management."""

from __future__ import annotations

import uuid

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import (
    get_current_user,
    get_current_workspace_id,
    require_workspace_owner_or_admin,
)
from app.core.domain.identity.models import User, Workspace
from app.core.domain.identity.services import is_super_admin_user
from app.dependencies import get_db
from app.exceptions import AppError


async def require_workspace_manager_or_super_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow workspace owner/admin or platform super admin to mutate users."""

    if await is_super_admin_user(session, user_id=user.id):
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("user.workspace_invalid", "Workspace not found", 404)
        return workspace_id
    return await require_workspace_owner_or_admin(
        workspace_id, user=user, session=session
    )


async def require_create_workspace_scope(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    token_workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> uuid.UUID:
    """Non-super-admin creates must target the JWT active workspace."""

    if await is_super_admin_user(session, user_id=user.id):
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("user.workspace_invalid", "Workspace not found", 404)
        return workspace_id
    if token_workspace_id != workspace_id:
        raise AppError(
            "auth.forbidden",
            "Cannot create users for a workspace other than the active one",
            403,
        )
    return await require_workspace_manager_or_super_admin(
        workspace_id, user=user, session=session
    )
