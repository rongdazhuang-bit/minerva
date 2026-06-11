"""Authorization dependencies for global dictionary management."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_any_workspace_member
from app.dependencies import get_db
from app.exceptions import AppError
from app.sys.tenant.api.deps import require_super_admin

__all__ = ["require_any_workspace_member", "require_super_admin"]


async def require_any_workspace_member(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow super-admin or any workspace member to read dictionaries."""

    if not await is_any_workspace_member(session, user_id=user.id):
        raise AppError(
            "auth.forbidden",
            "Only super-admin or workspace members can read dictionaries",
            403,
        )
    return user
