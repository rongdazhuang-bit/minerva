"""Route-level dependencies for workspace user management."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, get_current_workspace_id, _decode_access_payload
from app.core.domain.authorization.repository import is_tenant_admin
from app.core.domain.identity.models import MembershipRole, User, Workspace
from app.core.domain.identity.services import find_workspace_role_for_user
from app.core.security.permission_codes import TENANT_MEMBER_MANAGE
from app.core.security.permission_gateway import PermissionGateway
from app.core.security.permission_resolver import build_permission_context, parse_uuid_claim
from app.dependencies import get_db
from app.exceptions import AppError


async def _build_ctx(
    user: User,
    cred: HTTPAuthorizationCredentials,
    session: AsyncSession,
):
    """Build PermissionContext from bearer token."""

    payload = _decode_access_payload(cred)
    return await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )


async def require_workspace_manager_or_super_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow tenant admin, workspace admin, or platform super admin to mutate users."""

    if user.is_super_admin:
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("user.workspace_invalid", "Workspace not found", 404)
        return workspace_id
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise AppError("user.workspace_invalid", "Workspace not found", 404)
    if await is_tenant_admin(session, user_id=user.id, tenant_id=ws.tenant_id):
        return workspace_id
    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    ctx = await _build_ctx(user, cred, session)
    if PermissionGateway.has_perm(ctx, TENANT_MEMBER_MANAGE):
        if ctx.tenant_id is None or ctx.tenant_id == ws.tenant_id:
            return workspace_id
    role = await find_workspace_role_for_user(
        session, user_id=user.id, workspace_id=workspace_id
    )
    if role == MembershipRole.admin:
        return workspace_id
    raise AppError("auth.forbidden", "Only workspace admin can manage this resource", 403)


async def require_create_workspace_scope(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
    token_workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> uuid.UUID:
    """Non-super-admin creates must target the JWT active workspace."""

    if user.is_super_admin:
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
        workspace_id, user=user, cred=cred, session=session
    )
