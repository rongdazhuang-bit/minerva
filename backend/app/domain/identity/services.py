from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.identity.models import (
    MembershipRole,
    RefreshToken,
    Tenant,
    TenantMembership,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.exceptions import AppError
from app.infrastructure.security.password import hash_password, verify_password


@dataclass
class RegisterResult:
    user: User
    tenant: Tenant
    workspace: Workspace


async def register_user(
    session: AsyncSession, *, email: str, password: str
) -> RegisterResult:
    email = email.strip().lower()
    existing = await session.execute(select(User).where(User.email == email))
    if existing.scalar_one_or_none() is not None:
        raise AppError("auth.email_taken", "Email is already registered", 400)
    if len(password) < 8:
        raise AppError("auth.weak_password", "Password must be at least 8 characters", 400)
    user = User(email=email, password_hash=hash_password(password))
    short = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"组织-{short}", slug=f"t-{short}")
    session.add_all([user, tenant])
    await session.flush()
    workspace = Workspace(
        tenant_id=tenant.id,
        name="默认工作空间",
        slug="default",
    )
    session.add(workspace)
    await session.flush()
    session.add(
        TenantMembership(
            user_id=user.id,
            tenant_id=tenant.id,
            role=MembershipRole.owner,
        )
    )
    session.add(
        WorkspaceMembership(
            user_id=user.id,
            workspace_id=workspace.id,
            role=MembershipRole.owner,
        )
    )
    await session.commit()
    await session.refresh(user)
    await session.refresh(tenant)
    await session.refresh(workspace)
    return RegisterResult(user=user, tenant=tenant, workspace=workspace)


async def authenticate_user(
    session: AsyncSession, *, email: str, password: str
) -> tuple[User, Tenant, Workspace] | None:
    email = email.strip().lower()
    result = await session.execute(select(User).where(User.email == email))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(password, user.password_hash):
        return None
    ws_row = await session.execute(
        select(Workspace, Tenant)
        .select_from(Workspace)
        .join(Tenant, Tenant.id == Workspace.tenant_id)
        .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
        .where(WorkspaceMembership.user_id == user.id)
        .limit(1)
    )
    first = ws_row.first()
    if first is None:
        return None
    workspace, tenant = first
    return user, tenant, workspace


async def find_workspace_for_user(
    session: AsyncSession, *, user_id: uuid.UUID, workspace_id: uuid.UUID
) -> bool:
    r = await session.execute(
        select(WorkspaceMembership.id).where(
            WorkspaceMembership.user_id == user_id,
            WorkspaceMembership.workspace_id == workspace_id,
        )
    )
    return r.scalar_one_or_none() is not None


async def persist_refresh_token(
    session: AsyncSession, *, user_id: uuid.UUID, jti: uuid.UUID
) -> RefreshToken:
    from datetime import timedelta

    from app.config import settings

    now = datetime.now(UTC)
    expires = now + timedelta(days=settings.jwt_refresh_ttl_days)
    row = RefreshToken(user_id=user_id, jti=jti, expires_at=expires, revoked_at=None)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def get_refresh_by_jti(
    session: AsyncSession, *, jti: uuid.UUID, user_id: uuid.UUID
) -> RefreshToken | None:
    r = await session.execute(
        select(RefreshToken).where(RefreshToken.jti == jti, RefreshToken.user_id == user_id)
    )
    return r.scalar_one_or_none()


async def revoke_refresh_token_row(session: AsyncSession, jti: uuid.UUID) -> None:
    r = await session.execute(select(RefreshToken).where(RefreshToken.jti == jti))
    row = r.scalar_one_or_none()
    if row is not None and row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
        await session.commit()
