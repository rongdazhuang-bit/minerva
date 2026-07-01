"""Authorization dependencies for platform tenant management."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.authorization.repository import is_tenant_admin
from app.core.domain.identity.models import MembershipRole, User
from app.core.domain.identity.services import find_workspace_role_for_user
from app.core.security.permission_gateway import PermissionGateway, tenant_admin_action
from app.core.security.permission_resolver import build_permission_context, parse_uuid_claim
from app.dependencies import get_db
from app.exceptions import AppError

async def require_super_admin(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow only platform super administrators."""

    if not user.is_super_admin:
        raise AppError(
            "auth.forbidden",
            "Only super-admin can manage tenants",
            403,
        )
    return user


async def require_tenant_admin(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow platform super-admin or tenant administrator for one tenant."""

    if user.is_super_admin:
        return user
    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    if ctx.tenant_id is not None and ctx.tenant_id != tenant_id:
        raise AppError("auth.forbidden", "Wrong tenant context", 403)
    PermissionGateway.authorize(ctx, tenant_admin_action(tenant_id))
    return user


async def require_grant_manager(
    tenant_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Allow super-admin, tenant admin, or workspace admin grant managers."""

    if user.is_super_admin:
        return user
    if await is_tenant_admin(session, user_id=user.id, tenant_id=tenant_id):
        return user
    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    if ctx.tenant_id is not None and ctx.tenant_id != tenant_id:
        raise AppError("auth.forbidden", "Wrong tenant context", 403)
    if ctx.workspace_id is None or ctx.workspace_role != MembershipRole.admin:
        raise AppError("auth.forbidden", "Grant manager required", 403)
    if not await find_workspace_role_for_user(
        session, user_id=user.id, workspace_id=ctx.workspace_id
    ):
        raise AppError("auth.forbidden", "Grant manager required", 403)
    return user
