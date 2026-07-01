"""CRUD routes for the global sys_permission catalog."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.authorization import repository as auth_repo
from app.core.domain.authorization.models import SysPermission
from app.dependencies import get_db
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.permission.api.schemas import SysPermissionListPageOut, SysPermissionOut
from app.sys.tenant.api.deps import require_super_admin

router = APIRouter(prefix="/sys/permissions", tags=["permissions"])


def _row_to_out(row: SysPermission) -> SysPermissionOut:
    """Project one permission ORM row to the API schema."""

    return SysPermissionOut.model_validate(row)


@router.get("", response_model=SysPermissionListPageOut)
async def list_permissions(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=200),
    perm_type: str | None = Query(default=None),
    perm_code: str | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _admin=Depends(require_super_admin),
) -> SysPermissionListPageOut:
    """Return paginated rows from the global permission catalog."""

    rows, total = await auth_repo.list_permissions_page(
        session,
        page=page,
        page_size=page_size,
        perm_type=perm_type,
        perm_code=perm_code,
    )
    return SysPermissionListPageOut(
        items=[_row_to_out(row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
    )
