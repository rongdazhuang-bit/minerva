"""Platform-level routes for user list scope and capabilities."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import bearer, get_current_user, _decode_access_payload
from app.core.domain.identity.models import User
from app.core.security.permission_resolver import parse_uuid_claim
from app.dependencies import get_db
from app.sys.user.api.schemas import SysUserListCapabilitiesOut
from app.sys.user.service import user_service as svc

router = APIRouter(prefix="/sys/users", tags=["users"])


@router.get("/meta/capabilities", response_model=SysUserListCapabilitiesOut)
async def get_user_list_capabilities_route(
    user: User = Depends(get_current_user),
    cred: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_db),
) -> SysUserListCapabilitiesOut:
    """Return user list/form scope capability flags from JWT context."""

    tid: uuid.UUID | None = None
    wid: uuid.UUID | None = None
    if cred is not None:
        payload = _decode_access_payload(cred)
        tid = parse_uuid_claim(payload, "tid")
        wid = parse_uuid_claim(payload, "wid")
    data = await svc.get_user_list_capabilities(
        session,
        user_id=user.id,
        is_super_admin=user.is_super_admin,
        jwt_tenant_id=tid,
        jwt_workspace_id=wid,
    )
    return SysUserListCapabilitiesOut.model_validate(data)
