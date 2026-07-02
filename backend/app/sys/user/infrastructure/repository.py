"""Async queries for workspace members, user roles, and account cleanup."""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from sqlalchemy import delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.identity.models import (
    MembershipRole,
    RefreshToken,
    TenantMembership,
    User,
    Workspace,
    WorkspaceMembership,
)
from app.core.domain.authorization.models import GrantScopeType, GrantType, SysUserGrant
from app.sys.role.domain.db.models import SysRole


def _member_list_order():
    """Sort workspace members by account creation time descending."""

    return (User.created_at.desc(),)


def _apply_member_filters(
    stmt,
    *,
    workspace_id: uuid.UUID,
    email: str | None,
    nickname: str | None,
    phone: str | None,
    status: bool | None,
    membership_role: MembershipRole | None,
    role_id: uuid.UUID | None,
):
    """Apply optional list filters to a member query statement."""

    if email:
        stmt = stmt.where(User.email.ilike(f"%{email.strip()}%"))
    if nickname:
        stmt = stmt.where(User.nickname.ilike(f"%{nickname.strip()}%"))
    if phone:
        stmt = stmt.where(User.phone.ilike(f"%{phone.strip()}%"))
    if status is not None:
        stmt = stmt.where(User.status == status)
    if membership_role is not None:
        stmt = stmt.where(WorkspaceMembership.role == membership_role)
    if role_id is not None:
        stmt = stmt.where(
            User.id.in_(
                select(SysUserGrant.user_id).where(
                    SysUserGrant.role_id == role_id,
                    SysUserGrant.grant_type == GrantType.role.value,
                    SysUserGrant.scope_type == GrantScopeType.workspace.value,
                    SysUserGrant.scope_id == workspace_id,
                    SysUserGrant.status.is_(True),
                )
            )
        )
    return stmt


def _apply_tenant_member_filters(
    stmt,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    email: str | None,
    nickname: str | None,
    phone: str | None,
    status: bool | None,
    membership_role: MembershipRole | None,
    role_id: uuid.UUID | None,
):
    """Apply list filters for tenant-scoped workspace member queries."""

    stmt = stmt.where(Workspace.tenant_id == tenant_id)
    if workspace_id is not None:
        stmt = stmt.where(WorkspaceMembership.workspace_id == workspace_id)
    if email:
        stmt = stmt.where(User.email.ilike(f"%{email.strip()}%"))
    if nickname:
        stmt = stmt.where(User.nickname.ilike(f"%{nickname.strip()}%"))
    if phone:
        stmt = stmt.where(User.phone.ilike(f"%{phone.strip()}%"))
    if status is not None:
        stmt = stmt.where(User.status == status)
    if membership_role is not None:
        stmt = stmt.where(WorkspaceMembership.role == membership_role)
    if role_id is not None:
        scope_match = (
            SysUserGrant.scope_id == WorkspaceMembership.workspace_id
            if workspace_id is None
            else SysUserGrant.scope_id == workspace_id
        )
        stmt = stmt.where(
            User.id.in_(
                select(SysUserGrant.user_id).where(
                    SysUserGrant.role_id == role_id,
                    SysUserGrant.grant_type == GrantType.role.value,
                    SysUserGrant.scope_type == GrantScopeType.workspace.value,
                    scope_match,
                    SysUserGrant.status.is_(True),
                )
            )
        )
    return stmt


async def count_workspace_members(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> int:
    """Count users who are members of the given workspace."""

    stmt = (
        select(func.count())
        .select_from(User)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.user_id == User.id,
        )
        .where(WorkspaceMembership.workspace_id == workspace_id)
    )
    stmt = _apply_member_filters(
        stmt,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_workspace_members_page(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    limit: int,
    offset: int,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> Sequence[tuple[User, WorkspaceMembership]]:
    """Return one page of workspace members with membership rows."""

    stmt = (
        select(User, WorkspaceMembership)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.user_id == User.id,
        )
        .where(WorkspaceMembership.workspace_id == workspace_id)
        .order_by(*_member_list_order())
        .limit(limit)
        .offset(offset)
    )
    stmt = _apply_member_filters(
        stmt,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    result = await session.execute(stmt)
    return result.all()


async def count_tenant_workspace_members(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None = None,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> int:
    """Count workspace members under one tenant with optional workspace filter."""

    stmt = (
        select(func.count())
        .select_from(User)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
    )
    stmt = _apply_tenant_member_filters(
        stmt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one() or 0)


async def list_tenant_workspace_members_page(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    workspace_id: uuid.UUID | None,
    limit: int,
    offset: int,
    email: str | None = None,
    nickname: str | None = None,
    phone: str | None = None,
    status: bool | None = None,
    membership_role: MembershipRole | None = None,
    role_id: uuid.UUID | None = None,
) -> Sequence[tuple[User, WorkspaceMembership, Workspace]]:
    """Return one page of tenant-scoped workspace members."""

    stmt = (
        select(User, WorkspaceMembership, Workspace)
        .join(WorkspaceMembership, WorkspaceMembership.user_id == User.id)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
    )
    stmt = _apply_tenant_member_filters(
        stmt,
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        email=email,
        nickname=nickname,
        phone=phone,
        status=status,
        membership_role=membership_role,
        role_id=role_id,
    )
    stmt = stmt.order_by(*_member_list_order()).limit(limit).offset(offset)
    result = await session.execute(stmt)
    return result.all()


async def get_member_user(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> tuple[User, WorkspaceMembership] | None:
    """Load a user and membership when they belong to the workspace."""

    result = await session.execute(
        select(User, WorkspaceMembership)
        .join(
            WorkspaceMembership,
            WorkspaceMembership.user_id == User.id,
        )
        .where(
            WorkspaceMembership.workspace_id == workspace_id,
            User.id == user_id,
        )
    )
    row = result.first()
    if row is None:
        return None
    return row[0], row[1]


async def get_user_by_email(session: AsyncSession, *, email: str) -> User | None:
    """Load a user by normalized email."""

    result = await session.execute(
        select(User).where(User.email == email.strip().lower())
    )
    return result.scalar_one_or_none()


async def get_user_by_phone(session: AsyncSession, *, phone: str) -> User | None:
    """Load a user by phone when phone is non-empty."""

    normalized = phone.strip()
    if not normalized:
        return None
    result = await session.execute(select(User).where(User.phone == normalized))
    return result.scalar_one_or_none()


async def add_user(session: AsyncSession, row: User) -> User:
    """Insert a user row and flush."""

    session.add(row)
    await session.flush()
    return row


async def add_membership(
    session: AsyncSession, row: WorkspaceMembership
) -> WorkspaceMembership:
    """Insert a workspace membership row and flush."""

    session.add(row)
    await session.flush()
    return row


async def get_tenant_id_for_workspace(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> uuid.UUID | None:
    """Return the tenant id that owns the workspace, if the row exists."""

    result = await session.execute(
        select(Workspace.tenant_id).where(Workspace.id == workspace_id)
    )
    return result.scalar_one_or_none()


async def get_tenant_membership(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> TenantMembership | None:
    """Return one tenant membership row for a user, if present."""

    result = await session.execute(
        select(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def add_tenant_membership(
    session: AsyncSession, row: TenantMembership
) -> TenantMembership:
    """Insert a tenant membership row and flush."""

    session.add(row)
    await session.flush()
    return row


async def delete_tenant_membership(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> None:
    """Remove one user from one tenant."""

    await session.execute(
        delete(TenantMembership).where(
            TenantMembership.user_id == user_id,
            TenantMembership.tenant_id == tenant_id,
        )
    )
    await session.flush()


async def count_user_workspaces_in_tenant(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
) -> int:
    """Count workspace memberships the user still has under one tenant."""

    result = await session.execute(
        select(func.count())
        .select_from(WorkspaceMembership)
        .join(Workspace, Workspace.id == WorkspaceMembership.workspace_id)
        .where(
            WorkspaceMembership.user_id == user_id,
            Workspace.tenant_id == tenant_id,
        )
    )
    return int(result.scalar_one() or 0)


async def list_role_ids_for_user_in_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
    enabled_only: bool = False,
) -> list[uuid.UUID]:
    """Return sys_role ids assigned via workspace-scoped grants."""

    if tenant_id is None:
        tenant_id = await get_tenant_id_for_workspace(
            session, workspace_id=workspace_id
        )
    grant_stmt = select(SysUserGrant.role_id).where(
        SysUserGrant.user_id == user_id,
        SysUserGrant.grant_type == GrantType.role.value,
        SysUserGrant.status.is_(True),
        SysUserGrant.scope_type == GrantScopeType.workspace.value,
        SysUserGrant.scope_id == workspace_id,
        SysUserGrant.role_id.is_not(None),
    )
    if tenant_id is not None and enabled_only:
        grant_stmt = grant_stmt.where(
            SysUserGrant.role_id.in_(
                select(SysRole.id).where(
                    SysRole.tenant_id == tenant_id,
                    SysRole.status.is_(True),
                    or_(
                        SysRole.workspace_id.is_(None),
                        SysRole.workspace_id == workspace_id,
                    ),
                )
            )
        )
    result = await session.execute(grant_stmt)
    return list(result.scalars().all())


async def list_roles_for_user_in_workspace(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
) -> Sequence[SysRole]:
    """Return sys_role rows assigned via workspace-scoped grants."""

    if tenant_id is None:
        tenant_id = await get_tenant_id_for_workspace(
            session, workspace_id=workspace_id
        )
    if tenant_id is None:
        return []
    result = await session.execute(
        select(SysRole)
        .join(SysUserGrant, SysUserGrant.role_id == SysRole.id)
        .where(
            SysUserGrant.user_id == user_id,
            SysUserGrant.grant_type == GrantType.role.value,
            SysUserGrant.status.is_(True),
            SysUserGrant.scope_type == GrantScopeType.workspace.value,
            SysUserGrant.scope_id == workspace_id,
            SysRole.tenant_id == tenant_id,
            or_(
                SysRole.workspace_id.is_(None),
                SysRole.workspace_id == workspace_id,
            ),
        )
        .order_by(SysRole.role_sort.asc(), SysRole.create_at.desc())
    )
    return result.scalars().all()


async def delete_membership(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
) -> None:
    """Remove a user's membership from one workspace."""

    await session.execute(
        delete(WorkspaceMembership).where(
            WorkspaceMembership.workspace_id == workspace_id,
            WorkspaceMembership.user_id == user_id,
        )
    )
    await session.flush()


async def count_all_memberships_for_user(
    session: AsyncSession, *, user_id: uuid.UUID
) -> int:
    """Count how many workspaces a user belongs to."""

    result = await session.execute(
        select(func.count())
        .select_from(WorkspaceMembership)
        .where(WorkspaceMembership.user_id == user_id)
    )
    return int(result.scalar_one() or 0)


async def delete_all_memberships(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Delete every workspace membership for a user."""

    await session.execute(
        delete(WorkspaceMembership).where(WorkspaceMembership.user_id == user_id)
    )
    await session.flush()


async def delete_all_tenant_memberships(
    session: AsyncSession, *, user_id: uuid.UUID
) -> None:
    """Delete every tenant membership for a user."""

    await session.execute(
        delete(TenantMembership).where(TenantMembership.user_id == user_id)
    )
    await session.flush()


async def delete_refresh_tokens(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Delete refresh token rows for a user."""

    await session.execute(delete(RefreshToken).where(RefreshToken.user_id == user_id))
    await session.flush()


async def delete_user_row(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Delete the sys_user row."""

    row = await session.get(User, user_id)
    if row is not None:
        await session.delete(row)
        await session.flush()
