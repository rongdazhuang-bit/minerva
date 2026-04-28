from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.domain.identity.models import User
from app.pagination import DEFAULT_PAGE_SIZE
from app.sys.dict.api.schemas import (
    SysDictCreateIn,
    SysDictItemCreateIn,
    SysDictItemNodeOut,
    SysDictItemOut,
    SysDictItemPatchIn,
    SysDictListItemOut,
    SysDictListPageOut,
    SysDictPatchIn,
)
from app.sys.dict.domain.db.models import SysDict, SysDictItem
from app.sys.dict.service import dictionary_service as svc
from app.sys.dict.utils.item_tree import build_item_tree

router = APIRouter(prefix="/workspaces/{workspace_id}/dicts", tags=["dicts"])


def _dict_to_list_out(row: SysDict) -> SysDictListItemOut:
    return SysDictListItemOut(
        id=row.id,
        workspace_id=row.workspace_id,
        dict_code=row.dict_code,
        dict_name=row.dict_name,
        dict_sort=row.dict_sort,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _item_to_out(row: SysDictItem) -> SysDictItemOut:
    return SysDictItemOut(
        id=row.id,
        dict_uuid=row.dict_uuid,
        parent_uuid=row.parent_uuid,
        code=row.code,
        name=row.name,
        item_sort=row.item_sort,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _dict_patch(body: SysDictPatchIn) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {}
    for key, value in data.items():
        if key == "dict_code" and isinstance(value, str):
            patch[key] = value.strip()
        elif key == "dict_name" and isinstance(value, str):
            patch[key] = value.strip() or None
        else:
            patch[key] = value
    return patch


def _item_patch(body: SysDictItemPatchIn) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {}
    for key, value in data.items():
        if key == "code" and isinstance(value, str):
            patch[key] = value.strip()
        elif key == "name" and isinstance(value, str):
            patch[key] = value.strip()
        else:
            patch[key] = value
    return patch


@router.get(
    "",
    response_model=SysDictListPageOut,
    response_model_exclude_none=True,
)
async def list_dicts(
    workspace_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=100),
    code: str | None = Query(default=None, max_length=64),
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysDictListPageOut:
    raw_code = code.strip() if code else None
    rows, total = await svc.list_dicts_page(
        session,
        workspace_id=workspace_id,
        page=page,
        page_size=page_size,
        dict_code=raw_code,
    )
    item_tree_payload: list[SysDictItemNodeOut] | None = None
    if raw_code is not None and rows:
        flat = await svc.list_items_by_dict_code(
            session, workspace_id=workspace_id, dict_code=raw_code
        )
        item_tree_payload = build_item_tree(flat)

    out_items: list[SysDictListItemOut] = []
    for r in rows:
        base = _dict_to_list_out(r)
        if item_tree_payload is not None:
            out_items.append(base.model_copy(update={"item_tree": item_tree_payload}))
        else:
            out_items.append(base)
    return SysDictListPageOut(items=out_items, total=total)


@router.post("", response_model=SysDictListItemOut, status_code=status.HTTP_201_CREATED)
async def create_dict(
    workspace_id: uuid.UUID,
    body: SysDictCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysDictListItemOut:
    row = await svc.create_dict(
        session,
        workspace_id=workspace_id,
        dict_code=body.dict_code,
        dict_name=body.dict_name,
        dict_sort=body.dict_sort,
    )
    return _dict_to_list_out(row)


@router.patch("/{dict_id}", response_model=SysDictListItemOut)
async def patch_dict(
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    body: SysDictPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysDictListItemOut:
    patch = _dict_patch(body)
    if not patch:
        row = await svc.get_dict(session, workspace_id=workspace_id, dict_id=dict_id)
        return _dict_to_list_out(row)
    row = await svc.update_dict(
        session,
        workspace_id=workspace_id,
        dict_id=dict_id,
        patch=patch,
    )
    return _dict_to_list_out(row)


@router.delete("/{dict_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_dict(
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await svc.delete_dict(session, workspace_id=workspace_id, dict_id=dict_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{dict_id}/items", response_model=list[SysDictItemOut])
async def list_dict_items(
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[SysDictItemOut]:
    rows = await svc.list_items(
        session, workspace_id=workspace_id, dict_id=dict_id
    )
    return [_item_to_out(r) for r in rows]


@router.post(
    "/{dict_id}/items",
    response_model=SysDictItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_dict_item(
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    body: SysDictItemCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysDictItemOut:
    row = await svc.create_item(
        session,
        workspace_id=workspace_id,
        dict_id=dict_id,
        code=body.code,
        name=body.name,
        item_sort=body.item_sort,
        parent_uuid=body.parent_uuid,
    )
    return _item_to_out(row)


@router.patch("/{dict_id}/items/{item_id}", response_model=SysDictItemOut)
async def patch_dict_item(
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    item_id: uuid.UUID,
    body: SysDictItemPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> SysDictItemOut:
    patch = _item_patch(body)
    if not patch:
        row = await svc.get_item(
            session,
            workspace_id=workspace_id,
            dict_id=dict_id,
            item_id=item_id,
        )
        return _item_to_out(row)
    row = await svc.update_item(
        session,
        workspace_id=workspace_id,
        dict_id=dict_id,
        item_id=item_id,
        patch=patch,
    )
    return _item_to_out(row)


@router.delete(
    "/{dict_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_dict_item(
    workspace_id: uuid.UUID,
    dict_id: uuid.UUID,
    item_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await svc.delete_item(
        session,
        workspace_id=workspace_id,
        dict_id=dict_id,
        item_id=item_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
