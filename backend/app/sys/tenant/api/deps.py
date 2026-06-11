"""Authorization dependencies for platform tenant management."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_super_admin_user
from app.dependencies import get_db
from app.exceptions import AppError


async def require_super_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow only platform super administrators."""

    if not await is_super_admin_user(session, user_id=user.id):
        raise AppError(
            "auth.forbidden",
            "Only super-admin can manage tenants",
            403,
        )
    return user
