"""Build GraphAclActor from the authenticated user and workspace membership."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import User
from app.core.domain.identity.services import find_workspace_role_for_user
from app.graph_kb.domain.acl import GraphAclActor


async def actor_from_user(
    session: AsyncSession,
    *,
    user: User,
    workspace_id: uuid.UUID,
) -> GraphAclActor:
    """Resolve super-admin flag and workspace role into a GraphAclActor."""

    role = await find_workspace_role_for_user(
        session, user_id=user.id, workspace_id=workspace_id
    )
    return GraphAclActor(
        user_id=user.id,
        is_super_admin=bool(user.is_super_admin),
        workspace_role=role,
    )
