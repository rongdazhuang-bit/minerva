"""Authorization dependencies for global menu management."""

from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user
from app.core.domain.authorization.repository import has_any_tenant_admin_grant
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.exceptions import AppError


async def require_any_tenant_owner_or_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow super-admin or any tenant administrator grant holder."""

    if user.is_super_admin:
        return user
    if await has_any_tenant_admin_grant(session, user_id=user.id):
        return user
    raise AppError(
        "auth.forbidden",
        "Only super-admin or tenant admin can manage menus",
        403,
    )
