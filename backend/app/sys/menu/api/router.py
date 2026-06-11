"""CRUD routes for global sys_menu and sidebar navigation."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, get_current_workspace_id
from app.core.domain.identity.models import User
from app.dependencies import get_db
from app.sys.menu.api.deps import require_any_tenant_owner_or_admin
from app.sys.menu.api.schemas import (
    MenuDeleteOut,
    SysMenuCreateIn,
    SysMenuNodeOut,
    SysMenuOut,
    SysMenuPatchIn,
)
from app.sys.menu.domain.db.models import SysMenu
from app.sys.menu.service import menu_service as svc

router = APIRouter(prefix="/sys/menus", tags=["menus"])


def _row_to_out(row: SysMenu) -> SysMenuOut:
    return SysMenuOut.model_validate(row)


def _create_payload(body: SysMenuCreateIn) -> dict[str, Any]:
    return body.model_dump()


def _patch_payload(body: SysMenuPatchIn) -> dict[str, Any]:
    return body.model_dump(exclude_unset=True)


@router.get("", response_model=list[SysMenuNodeOut])
async def list_menus(
    menu_name: str | None = Query(default=None),
    status: bool | None = Query(default=None),
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_any_tenant_owner_or_admin),
) -> list[SysMenuNodeOut]:
    """Return admin menu tree with optional filters."""

    return await svc.list_menu_tree(session, menu_name=menu_name, status=status)


@router.get("/nav", response_model=list[SysMenuNodeOut])
async def list_nav(
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    workspace_id: uuid.UUID = Depends(get_current_workspace_id),
) -> list[SysMenuNodeOut]:
    """Return sidebar navigation tree for the current user."""

    return await svc.list_nav_tree_for_user(
        session,
        user_id=user.id,
        workspace_id=workspace_id,
    )


@router.post("", response_model=SysMenuOut, status_code=201)
async def create_menu(
    body: SysMenuCreateIn,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_any_tenant_owner_or_admin),
) -> SysMenuOut:
    """Create a global menu row."""

    row = await svc.create_menu(session, _create_payload(body))
    return _row_to_out(row)


@router.patch("/{menu_id}", response_model=SysMenuOut)
async def patch_menu(
    menu_id: uuid.UUID,
    body: SysMenuPatchIn,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_any_tenant_owner_or_admin),
) -> SysMenuOut:
    """Partially update a menu row."""

    row = await svc.update_menu(session, menu_id, _patch_payload(body))
    return _row_to_out(row)


@router.delete("/{menu_id}", response_model=MenuDeleteOut)
async def delete_menu(
    menu_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_any_tenant_owner_or_admin),
) -> MenuDeleteOut:
    """Cascade-delete a menu and all descendants."""

    deleted_count = await svc.delete_menu_cascade(session, menu_id)
    return MenuDeleteOut(deleted_count=deleted_count)
