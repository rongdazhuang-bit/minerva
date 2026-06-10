"""Authorization dependencies for global menu management."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.identity.models import User
from app.core.domain.identity.services import is_any_tenant_owner_or_admin
from app.dependencies import get_db
from app.exceptions import AppError


async def require_any_tenant_owner_or_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow only users who are tenant owner or admin in any tenant."""

    if not await is_any_tenant_owner_or_admin(session, user_id=user.id):
        raise AppError(
            "auth.forbidden",
            "Only super-admin or tenant owner/admin can manage menus",
            403,
        )
    return user
