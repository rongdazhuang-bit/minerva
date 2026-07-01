"""Dependency helpers for JWT bearer auth and workspace authorization gates."""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.core.domain.identity.models import MembershipRole, User, Workspace
from app.core.domain.identity.services import (
    find_tenant_role_for_user,
    find_workspace_for_user,
    find_workspace_role_for_user,
)
from app.exceptions import AppError
from app.core.infrastructure.security.jwt_tokens import decode_token

# Optional Bearer extractor so routes can return 401 instead of FastAPI's default 403 when absent.
bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
    """Resolve the signed-in user from an access JWT or raise ``AppError``."""

    if cred is None or cred.scheme.lower() != "bearer":
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    try:
        payload = decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise AppError("auth.invalid_token", "Invalid or expired token", 401) from None
    if payload.get("type") != "access":
        raise AppError("auth.invalid_token", "Not an access token", 401)
    uid = uuid.UUID(str(payload["sub"]))
    user = await session.get(User, uid)
    if user is None:
        raise AppError("auth.invalid_token", "User not found", 401)
    if not user.status:
        raise AppError("user.disabled", "User account is disabled", 401)
    return user


def _decode_access_payload(cred: HTTPAuthorizationCredentials) -> dict:
    """Decode a Bearer access token or raise ``AppError``."""

    if cred.scheme.lower() != "bearer":
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    try:
        payload = decode_token(cred.credentials)
    except jwt.PyJWTError:
        raise AppError("auth.invalid_token", "Invalid or expired token", 401) from None
    if payload.get("type") != "access":
        raise AppError("auth.invalid_token", "Not an access token", 401)
    return payload


async def get_current_workspace_id(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> uuid.UUID:
    """Resolve active workspace id from the access JWT ``wid`` claim."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    wid = payload.get("wid")
    if wid is None:
        raise AppError("auth.invalid_token", "Missing workspace context in token", 401)
    return uuid.UUID(str(wid))


async def require_workspace_member(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Use on routes that declare path param `workspace_id`; membership is checked."""
    if user.is_super_admin:
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("auth.forbidden", "Workspace not found", 403)
        return workspace_id
    if not await find_workspace_for_user(session, user_id=user.id, workspace_id=workspace_id):
        raise AppError("auth.forbidden", "Not a member of this workspace", 403)
    return workspace_id


async def require_workspace_owner_or_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Ensure ``user`` is workspace admin (or platform super-admin)."""

    if user.is_super_admin:
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("auth.forbidden", "Workspace not found", 403)
        return workspace_id
    role = await find_workspace_role_for_user(
        session, user_id=user.id, workspace_id=workspace_id
    )
    if role is None:
        raise AppError("auth.forbidden", "Not a member of this workspace", 403)
    if role != MembershipRole.admin:
        raise AppError("auth.forbidden", "Only workspace admin can manage this resource", 403)
    return workspace_id


async def require_tenant_owner_or_admin(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Ensure user is tenant admin (membership or grant) for the workspace's tenant."""

    if user.is_super_admin:
        ws = await session.get(Workspace, workspace_id)
        if ws is None:
            raise AppError("auth.forbidden", "Workspace not found", 403)
        return workspace_id
    if not await find_workspace_for_user(
        session, user_id=user.id, workspace_id=workspace_id
    ):
        raise AppError("auth.forbidden", "Not a member of this workspace", 403)
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise AppError("auth.forbidden", "Workspace not found", 403)
    role = await find_tenant_role_for_user(
        session, user_id=user.id, tenant_id=ws.tenant_id
    )
    if role is None:
        raise AppError("auth.forbidden", "Not a member of this tenant", 403)
    if role != MembershipRole.admin:
        from app.core.domain.authorization.repository import is_tenant_admin

        if not await is_tenant_admin(
            session, user_id=user.id, tenant_id=ws.tenant_id
        ):
            raise AppError("skills.forbidden", "Only tenant admin can manage skills", 403)
    return workspace_id
