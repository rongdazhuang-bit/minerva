from __future__ import annotations

import uuid

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.domain.identity.models import User
from app.domain.identity.services import find_workspace_for_user
from app.exceptions import AppError
from app.infrastructure.security.jwt_tokens import decode_token

bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> User:
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
    return user


async def require_workspace_member(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Use on routes that declare path param `workspace_id`; membership is checked."""
    if not await find_workspace_for_user(session, user_id=user.id, workspace_id=workspace_id):
        raise AppError("auth.forbidden", "Not a member of this workspace", 403)
    return workspace_id
