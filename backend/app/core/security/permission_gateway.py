"""Central authorization decision engine."""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from app.core.domain.identity.models import MembershipRole, Workspace
from app.core.domain.identity.services import find_workspace_for_user
from app.core.security.permission_codes import (
    TENANT_ADMIN_IMPLICIT_PERMS,
    TENANT_MEMBER_MANAGE,
    TENANT_ROLE_MANAGE,
    WORKSPACE_MANAGE,
)
from app.core.security.permission_context import PermissionContext
from app.exceptions import AppError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security.permission_resolver import workspace_belongs_to_tenant


@dataclass(frozen=True)
class PermissionAction:
    """One authorization check against a PermissionContext."""

    perm_code: str | None = None
    feature_code: str | None = None
    workspace_id: uuid.UUID | None = None
    tenant_id: uuid.UUID | None = None
    require_workspace_manage: bool = False
    require_tenant_admin: bool = False
    require_super_admin: bool = False


class PermissionGateway:
    """Evaluate PermissionAction against a built PermissionContext."""

    @staticmethod
    def authorize(ctx: PermissionContext, action: PermissionAction) -> None:
        """Allow or raise ``AppError`` with code ``auth.forbidden``."""

        if ctx.is_super_admin:
            return

        if action.require_super_admin:
            raise AppError("auth.forbidden", "Super admin required", 403)

        if action.feature_code and action.feature_code not in ctx.tenant_features:
            raise AppError(
                "auth.forbidden",
                "Feature not enabled for tenant",
                403,
            )

        PermissionGateway._check_data_scope(ctx, action)

        if action.require_tenant_admin and not ctx.is_tenant_admin:
            raise AppError("auth.forbidden", "Tenant admin required", 403)

        if action.require_workspace_manage:
            PermissionGateway._require_workspace_admin(ctx, action.workspace_id)

        if action.perm_code:
            PermissionGateway._require_perm(ctx, action.perm_code)

    @staticmethod
    def has_perm(ctx: PermissionContext, perm_code: str) -> bool:
        """Return True when the context includes the permission code."""

        if ctx.is_super_admin or "*" in ctx.permissions:
            return True
        if perm_code in ctx.permissions:
            return True
        if ctx.is_tenant_admin and perm_code in TENANT_ADMIN_IMPLICIT_PERMS:
            return True
        if perm_code == WORKSPACE_MANAGE and ctx.workspace_role == MembershipRole.admin:
            return True
        return False

    @staticmethod
    def _require_perm(ctx: PermissionContext, perm_code: str) -> None:
        if not PermissionGateway.has_perm(ctx, perm_code):
            raise AppError("auth.forbidden", "Permission denied", 403)

    @staticmethod
    def _require_workspace_admin(
        ctx: PermissionContext, workspace_id: uuid.UUID | None
    ) -> None:
        if workspace_id is None:
            raise AppError("auth.forbidden", "Workspace required", 403)
        if ctx.workspace_id != workspace_id:
            raise AppError("auth.forbidden", "Wrong workspace context", 403)
        if ctx.workspace_role != MembershipRole.admin:
            raise AppError("auth.forbidden", "Workspace admin required", 403)

    @staticmethod
    def _check_data_scope(ctx: PermissionContext, action: PermissionAction) -> None:
        wid = action.workspace_id
        if wid is None:
            return
        if ctx.workspace_id is not None and ctx.workspace_id != wid:
            raise AppError("auth.forbidden", "Wrong workspace context", 403)
        if action.tenant_id and ctx.tenant_id and ctx.tenant_id != action.tenant_id:
            raise AppError("auth.forbidden", "Wrong tenant context", 403)


async def require_data_scope_membership(
    session: AsyncSession,
    ctx: PermissionContext,
    *,
    workspace_id: uuid.UUID,
    tenant_id: uuid.UUID | None = None,
) -> None:
    """Ensure non-super-admin users belong to the target workspace."""

    if ctx.is_super_admin:
        if tenant_id is not None:
            ok = await workspace_belongs_to_tenant(
                session, workspace_id=workspace_id, tenant_id=tenant_id
            )
            if not ok:
                raise AppError("auth.forbidden", "Workspace not in tenant", 403)
        return

    if not await find_workspace_for_user(
        session, user_id=ctx.user_id, workspace_id=workspace_id
    ):
        from app.core.domain.authorization.repository import is_tenant_admin

        ws = await session.get(Workspace, workspace_id)
        if ws is None or not await is_tenant_admin(
            session, user_id=ctx.user_id, tenant_id=ws.tenant_id
        ):
            raise AppError("auth.forbidden", "Not a member of this workspace", 403)

    if tenant_id is not None:
        ok = await workspace_belongs_to_tenant(
            session, workspace_id=workspace_id, tenant_id=tenant_id
        )
        if not ok:
            raise AppError("auth.forbidden", "Workspace not in tenant", 403)


def workspace_manage_action(workspace_id: uuid.UUID) -> PermissionAction:
    """Build a workspace admin management check."""

    return PermissionAction(
        perm_code=WORKSPACE_MANAGE,
        workspace_id=workspace_id,
        require_workspace_manage=True,
    )


def tenant_admin_action(tenant_id: uuid.UUID) -> PermissionAction:
    """Build a tenant administrator check."""

    return PermissionAction(
        perm_code=TENANT_MEMBER_MANAGE,
        tenant_id=tenant_id,
        require_tenant_admin=True,
    )
