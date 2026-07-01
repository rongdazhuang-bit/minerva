"""Route-level dependencies for workspace role management."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.authorization.repository import is_tenant_admin
from app.core.domain.identity.models import User, Workspace
from app.core.security.permission_codes import TENANT_ROLE_MANAGE
from app.core.security.permission_gateway import PermissionAction, PermissionGateway
from app.core.security.permission_resolver import build_permission_context, parse_uuid_claim
from app.dependencies import get_db
from app.exceptions import AppError


async def require_tenant_role_manager(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow tenant admin or platform super admin to mutate workspace roles."""

    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise AppError("role.workspace_invalid", "Workspace not found", 404)
    if user.is_super_admin:
        return workspace_id
    if await is_tenant_admin(session, user_id=user.id, tenant_id=ws.tenant_id):
        return workspace_id
    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    PermissionGateway.authorize(
        ctx,
        PermissionAction(
            perm_code=TENANT_ROLE_MANAGE,
            tenant_id=ws.tenant_id,
            require_tenant_admin=True,
        ),
    )
    return workspace_id
