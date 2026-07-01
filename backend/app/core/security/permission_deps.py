"""FastAPI dependencies wrapping PermissionGateway."""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user
from app.core.domain.identity.models import User
from app.core.infrastructure.security.jwt_tokens import decode_token
from app.core.security.permission_context import PermissionContext
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

_bearer = bearer


def _decode_access_payload(cred: HTTPAuthorizationCredentials) -> dict:
    """Decode bearer access token or raise ``AppError``."""

    if cred.scheme.lower() != "bearer":
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    try:
        payload = decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise AppError("auth.invalid_token", "Invalid or expired token", 401) from None
    if payload.get("type") != "access":
        raise AppError("auth.invalid_token", "Not an access token", 401)
    return payload


async def get_permission_context(
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> PermissionContext:
    """Build PermissionContext for the current request."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    tenant_id = parse_uuid_claim(payload, "tid")
    workspace_id = parse_uuid_claim(payload, "wid")
    return await build_permission_context(
        session,
        user=user,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
    )


async def require_data_scope(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Allow super-admin or workspace member access to ``workspace_id``."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    await require_data_scope_membership(session, ctx, workspace_id=workspace_id)
    return workspace_id


async def require_permission(
    perm_code: str,
    workspace_id: uuid.UUID | None = None,
    feature_code: str | None = None,
    *,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> PermissionContext:
    """Run PermissionGateway for one permission code."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    wid = workspace_id or ctx.workspace_id
    action = PermissionAction(
        perm_code=perm_code,
        feature_code=feature_code,
        workspace_id=wid,
        tenant_id=ctx.tenant_id,
    )
    if wid is not None:
        await require_data_scope_membership(session, ctx, workspace_id=wid)
    PermissionGateway.authorize(ctx, action)
    return ctx


async def require_workspace_manage(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(_bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Require workspace admin (or super-admin) for mutating workspace resources."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    await require_data_scope_membership(session, ctx, workspace_id=workspace_id)
    from app.core.security.permission_gateway import workspace_manage_action

    PermissionGateway.authorize(ctx, workspace_manage_action(workspace_id))
    return workspace_id
