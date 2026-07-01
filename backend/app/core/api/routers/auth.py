"""Authentication routes: signup, login, and refresh-token rotation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import jwt
from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db
from app.core.domain.identity.models import (
    Tenant,
    TenantMembership,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.core.domain.identity.services import (
    authenticate_user,
    get_refresh_by_jti,
    persist_refresh_token,
    register_user,
    revoke_refresh_token_row,
)
from app.exceptions import AppError
from app.config import settings
from app.core.infrastructure.security.jwt_tokens import (
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.core.infrastructure.security.login_captcha import (
    create_login_captcha,
    create_register_captcha,
    verify_login_captcha,
    verify_register_captcha,
)
from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.security.permission_resolver import (
    build_permission_context,
    parse_uuid_claim,
)
from app.sys.menu.infrastructure import repository as menu_repo

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    """Credential payload for ``POST /auth/register``."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=200)
    captcha_id: str = ""
    captcha_code: str = ""


class LoginIn(BaseModel):
    """Credential payload for ``POST /auth/login``."""

    email: EmailStr
    password: str
    captcha_id: str = ""
    captcha_code: str = ""


class AuthCaptchaOut(BaseModel):
    """CAPTCHA challenge for login or register forms."""

    captcha_id: str
    image: str


class RefreshIn(BaseModel):
    """Opaque refresh token body for ``POST /auth/refresh``."""

    refresh_token: str


class TokenOut(BaseModel):
    """Bearer pair returned after successful auth."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AuthorizationOut(BaseModel):
    """Effective permissions summary for the authenticated user."""

    email: str
    is_super_admin: bool
    tenant_id: uuid.UUID | None = None
    tenant_name: str | None = None
    workspace_id: uuid.UUID | None = None
    workspace_role: str | None = None
    tenant_role: str | None = None
    is_tenant_admin: bool
    tenant_features: list[str]
    permissions: list[str]
    menu_paths: list[str]


async def _issue_tokens(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID,
) -> tuple[TokenOut, uuid.UUID]:
    """Create access/refresh tokens after validating workspace membership."""

    user = await session.get(User, user_id)
    if user is None:
        raise AppError("auth.invalid_token", "User not found", 401)

    jti = uuid.uuid4()
    r = await session.execute(
        select(WorkspaceMembership.role).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    wrole = r.scalar_one_or_none()
    if wrole is None and not user.is_super_admin:
        raise AppError("auth.no_workspace_membership", "No workspace membership for user", 401)
    tr = await session.execute(
        select(TenantMembership.role).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    trole = tr.scalar_one_or_none()
    access = create_access_token(
        user_id=user_id,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        workspace_role=wrole.value if wrole is not None else None,
        tenant_role=trole.value if trole is not None else None,
        is_super_admin=bool(user.is_super_admin),
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
    """Register a user and return freshly minted bearer tokens."""

    if settings.auth_login_captcha_enabled:
        verify_register_captcha(body.captcha_id, body.captcha_code)
    r = await register_user(session, email=body.email, password=body.password)
    out, jti = await _issue_tokens(
        session,
        user_id=r.user.id,
        tenant_id=r.tenant.id,
        workspace_id=r.workspace.id,
    )
    await persist_refresh_token(session, user_id=r.user.id, jti=jti)
    return out


@router.get("/login/captcha", response_model=AuthCaptchaOut)
async def login_captcha() -> AuthCaptchaOut:
    """Return a one-time SVG CAPTCHA image for the login form."""

    if not settings.auth_login_captcha_enabled:
        raise AppError("auth.captcha_disabled", "Login captcha is disabled", 404)
    captcha_id, image = create_login_captcha()
    return AuthCaptchaOut(captcha_id=captcha_id, image=image)


@router.get("/register/captcha", response_model=AuthCaptchaOut)
async def register_captcha() -> AuthCaptchaOut:
    """Return a one-time SVG CAPTCHA image for the register form."""

    if not settings.auth_login_captcha_enabled:
        raise AppError("auth.captcha_disabled", "Register captcha is disabled", 404)
    captcha_id, image = create_register_captcha()
    return AuthCaptchaOut(captcha_id=captcha_id, image=image)


@router.post("/login", response_model=TokenOut)
async def login(body: LoginIn, session: AsyncSession = Depends(get_db)) -> TokenOut:
    """Authenticate existing credentials and persist a new refresh row."""

    if settings.auth_login_captcha_enabled:
        verify_login_captcha(body.captcha_id, body.captcha_code)
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
    """Rotate refresh token after validating stored row and workspace membership."""

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
    if not u.status:
        raise AppError("user.disabled", "User account is disabled", 401)
    wsm = await session.execute(
        select(Workspace, Tenant)
        .select_from(Workspace)
        .join(Tenant, Tenant.id == Workspace.tenant_id)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == uid)
        .limit(1)
    )
    first = wsm.first()
    if first is None and u.is_super_admin:
        wsm = await session.execute(
            select(Workspace, Tenant)
            .select_from(Workspace)
            .join(Tenant, Tenant.id == Workspace.tenant_id)
            .where(Tenant.status.is_(True), Workspace.status.is_(True))
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


@router.get("/me/authorization", response_model=AuthorizationOut)
async def me_authorization(
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> AuthorizationOut:
    """Return effective permissions for the current access token."""

    if cred is None:
        raise AppError("auth.missing_token", "Authorization Bearer token required", 401)
    payload = _decode_access_payload(cred)
    ctx = await build_permission_context(
        session,
        user=user,
        tenant_id=parse_uuid_claim(payload, "tid"),
        workspace_id=parse_uuid_claim(payload, "wid"),
    )
    menu_paths: list[str] = []
    if ctx.menu_ids:
        rows = await menu_repo.list_all(session)
        by_id = {r.id: r for r in rows}
        menu_paths = sorted(
            {
                str(by_id[mid].path)
                for mid in ctx.menu_ids
                if mid in by_id and by_id[mid].path
            }
        )
    perms = sorted(ctx.permissions) if "*" not in ctx.permissions else ["*"]
    tenant_name: str | None = None
    if ctx.tenant_id is not None:
        tenant = await session.get(Tenant, ctx.tenant_id)
        if tenant is not None:
            tenant_name = tenant.name
    return AuthorizationOut(
        email=user.email,
        is_super_admin=ctx.is_super_admin,
        tenant_id=ctx.tenant_id,
        tenant_name=tenant_name,
        workspace_id=ctx.workspace_id,
        workspace_role=ctx.workspace_role.value if ctx.workspace_role else None,
        tenant_role=ctx.tenant_role.value if ctx.tenant_role else None,
        is_tenant_admin=ctx.is_tenant_admin,
        tenant_features=sorted(ctx.tenant_features),
        permissions=perms,
        menu_paths=menu_paths,
    )
