"""Authorization dependencies for dataset module routes."""

from __future__ import annotations

import uuid

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.identity.models import User
from app.core.security.permission_codes import FEATURE_DATASET
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


async def require_dataset_workspace(
    workspace_id: uuid.UUID,
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> uuid.UUID:
    """Require workspace membership and enabled dataset feature entitlement."""

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
    PermissionGateway.authorize(
        ctx,
        PermissionAction(feature_code=FEATURE_DATASET, workspace_id=workspace_id),
    )
    return workspace_id
