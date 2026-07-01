"""Build PermissionContext and resolve navigation permissions."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization import repository as auth_repo
from app.core.domain.identity.models import MembershipRole, User, Workspace
from app.core.domain.identity.services import (
    find_tenant_role_for_user,
    find_workspace_for_user,
    find_workspace_role_for_user,
)
from app.core.security.permission_codes import TENANT_ADMIN_IMPLICIT_PERMS
from app.core.security.permission_context import PermissionContext
from app.sys.menu.infrastructure import repository as menu_repo


async def build_permission_context(
    session: AsyncSession,
    *,
    user: User,
    tenant_id: uuid.UUID | None,
    workspace_id: uuid.UUID | None,
) -> PermissionContext:
    """Assemble effective permissions from JWT context and authorization tables."""

    tenant_role: MembershipRole | None = None
    workspace_role: MembershipRole | None = None
    if tenant_id is not None:
        tenant_role = await find_tenant_role_for_user(
            session, user_id=user.id, tenant_id=tenant_id
        )
    if workspace_id is not None:
        workspace_role = await find_workspace_role_for_user(
            session, user_id=user.id, workspace_id=workspace_id
        )

    is_tenant_admin = False
    tenant_features: frozenset[str] = frozenset()
    if user.is_super_admin:
        tenant_features = frozenset(await auth_repo.load_enabled_tenant_features(
            session, tenant_id=tenant_id
        )) if tenant_id else frozenset()
    elif tenant_id is not None:
        is_tenant_admin = await auth_repo.is_tenant_admin(
            session, user_id=user.id, tenant_id=tenant_id
        )
        tenant_features = frozenset(
            await auth_repo.load_enabled_tenant_features(session, tenant_id=tenant_id)
        )

    permissions: set[str] = set()
    menu_ids: set[uuid.UUID] = set()

    if user.is_super_admin:
        from app.sys.menu.service.menu_service import filter_nav_rows

        all_rows = await menu_repo.list_all(session)
        menu_ids = {r.id for r in filter_nav_rows(all_rows)}
        permissions.add("*")
    elif workspace_id is not None:
        role_ids = await auth_repo.load_role_ids_from_grants(
            session,
            user_id=user.id,
            workspace_id=workspace_id,
            tenant_id=tenant_id,
        )
        permissions |= await auth_repo.load_permission_codes_for_roles(
            session, role_ids=role_ids
        )
        permissions |= await auth_repo.load_direct_permission_codes(
            session,
            user_id=user.id,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
        )
        if is_tenant_admin:
            permissions |= set(TENANT_ADMIN_IMPLICIT_PERMS)
        from app.sys.menu.service.menu_service import (
            expand_allowed_nav_menu_ids,
            filter_nav_rows,
        )

        all_rows = await menu_repo.list_all(session)
        granted_menu_ids = await auth_repo.load_menu_ids_for_roles_dual(
            session, role_ids=role_ids
        )
        menu_ids = expand_allowed_nav_menu_ids(all_rows, granted_menu_ids)

    return PermissionContext(
        user_id=user.id,
        is_super_admin=bool(user.is_super_admin),
        tenant_id=tenant_id,
        workspace_id=workspace_id,
        tenant_role=tenant_role,
        workspace_role=workspace_role,
        is_tenant_admin=is_tenant_admin,
        tenant_features=tenant_features,
        permissions=frozenset(permissions),
        menu_ids=frozenset(menu_ids),
    )


async def workspace_belongs_to_tenant(
    session: AsyncSession, *, workspace_id: uuid.UUID, tenant_id: uuid.UUID
) -> bool:
    """True when the workspace row exists under the given tenant."""

    ws = await session.get(Workspace, workspace_id)
    return ws is not None and ws.tenant_id == tenant_id


def parse_uuid_claim(payload: dict[str, Any], key: str) -> uuid.UUID | None:
    """Parse an optional UUID claim from a JWT payload."""

    raw = payload.get(key)
    if raw is None:
        return None
    return uuid.UUID(str(raw))
