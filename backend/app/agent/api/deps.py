"""Authorization dependencies for agent module routes."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.identity.models import User, Workspace
from app.core.security.permission_codes import FEATURE_AGENT, FEATURE_SKILLS
from app.core.security.permission_deps import make_require_feature_workspace
from app.core.security.permission_gateway import (
    PermissionAction,
    PermissionGateway,
    require_data_scope_membership,
)
from app.core.security.permission_resolver import (
    build_permission_context,
    parse_uuid_claim,
)
from app.dependencies import get_db
from app.exceptions import AppError

require_agent_workspace = make_require_feature_workspace(FEATURE_AGENT)
require_agent_skills_workspace = make_require_feature_workspace(FEATURE_SKILLS)


async def require_skills_tenant_manager(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Require skills feature entitlement and tenant administrator grant."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise AppError("auth.forbidden", "Workspace not found", 403)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    await require_data_scope_membership(session, ctx, workspace_id=workspace_id)
    PermissionGateway.authorize(
        ctx,
        PermissionAction(
            feature_code=FEATURE_SKILLS,
            workspace_id=workspace_id,
            tenant_id=ws.tenant_id,
            require_tenant_admin=True,
        ),
    )
    return workspace_id
