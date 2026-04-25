from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.domain.identity.models import (
    Tenant,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.domain.identity.services import (
    authenticate_user,
    get_refresh_by_jti,
    persist_refresh_token,
    register_user,
    revoke_refresh_token_row,
)
from app.exceptions import AppError
from app.infrastructure.security.jwt_tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class RefreshIn(BaseModel):
    refresh_token: str


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


async def _issue_tokens(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> tuple[TokenOut, uuid.UUID]:
    jti = uuid.uuid4()
    r = await session.execute(
        select(WorkspaceMembership.role).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    wrole = r.scalar_one_or_none()
    if wrole is None:
        raise AppError("auth.no_workspace_membership", "No workspace membership for user", 401)
    access = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        workspace_role=wrole.value,
    )
    refresh = create_refresh_token(user_id=user_id, jti=jti)
    return (
        TokenOut(
            access_token=access,
            refresh_token=refresh,
        ),
        jti,
    )


@router.post("/register", response_model=TokenOut, status_code=201)
async def register(body: RegisterIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    r = await register_user(session, email=body.email, password=body.password)
    out, jti = await _issue_tokens(
        session,
        user_id=r.user.id,
        tenant_id=r.tenant.id,
        workspace_id=r.workspace.id,
    )
    await persist_refresh_token(session, user_id=r.user.id, jti=jti)
    return out


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    out = await authenticate_user(session, email=body.email, password=body.password)
    if out is None:
        raise AppError("auth.invalid_credentials", "Invalid email or password", 401)
    user, tenant, workspace = out
    tok, jti = await _issue_tokens(
        session,
        user_id=user.id,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
    )
    await persist_refresh_token(session, user_id=user.id, jti=jti)
    return tok


@router.post("/refresh", response_model=TokenOut)
async def refresh(body: RefreshIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    try:
        payload = decode_token(body.refresh_token)
    except jwt.PyJWTError as e:
        raise AppError("auth.invalid_token", "Invalid refresh token", 401) from e
    if payload.get("type") != "refresh":
        raise AppError("auth.invalid_token", "Not a refresh token", 401)
    uid = uuid.UUID(str(payload["sub"]))
    jti = uuid.UUID(str(payload["jti"]))
    row = await get_refresh_by_jti(session, jti=jti, user_id=uid)
    if row is None or row.revoked_at is not None:
        raise AppError("auth.refresh_reused", "Refresh token is invalid or revoked", 401)
    exp = row.expires_at
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=UTC)
    if exp < datetime.now(UTC):
        raise AppError("auth.invalid_token", "Refresh token expired", 401)
    u = await session.get(User, uid)
    if u is None:
        raise AppError("auth.invalid_token", "User not found", 401)
    wsm = await session.execute(
        select(Workspace, Tenant)
        .select_from(Workspace)
        .join(Tenant, Tenant.id == Workspace.tenant_id)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == uid)
        .limit(1)
    )
    first = wsm.first()
    if first is None:
        raise AppError("auth.invalid_token", "No workspace for user", 401)
    workspace, tenant = first
    await revoke_refresh_token_row(session, jti)
    tok, new_j = await _issue_tokens(
        session,
        user_id=uid,
        tenant_id=tenant.id,
        workspace_id=workspace.id,
    )
    await persist_refresh_token(session, user_id=uid, jti=new_j)
    return tok
