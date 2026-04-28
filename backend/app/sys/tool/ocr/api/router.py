from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_workspace_member
from app.dependencies import get_db
from app.domain.identity.models import User
from app.sys.tool.ocr.api.schemas import (
    OcrToolCreateIn,
    OcrToolDetailOut,
    OcrToolListItemOut,
    OcrToolPatchIn,
)
from app.sys.tool.ocr.domain.db.models import SysOcrTool
from app.sys.tool.ocr.service.ocr_tool_service import (
    create_tool,
    delete_tool,
    get_tool,
    list_tools,
    update_tool,
)

router = APIRouter(prefix="/workspaces/{workspace_id}/ocr-tools", tags=["ocr-tools"])

_LEGACY_OCR_AUTH_TO_CANON: dict[str, str] = {
    "none": "NONE",
    "basic": "BASIC",
    "api_key": "API_KEY",
}


def _normalize_ocr_auth_type(value: str | None) -> str | None:
    if value is None:
        return None
    s = value.strip()
    if not s:
        return None
    return _LEGACY_OCR_AUTH_TO_CANON.get(s.lower(), s)


def _to_list_item(row: SysOcrTool) -> OcrToolListItemOut:
    return OcrToolListItemOut(
        id=row.id,
        name=row.name,
        url=row.url,
        auth_type=row.auth_type,
        user_name=row.user_name,
        remark=row.remark,
        has_api_key=bool(row.api_key),
        has_password=bool(row.user_passwd),
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_detail(row: SysOcrTool) -> OcrToolDetailOut:
    return OcrToolDetailOut(
        id=row.id,
        workspace_id=row.workspace_id,
        name=row.name,
        url=row.url,
        auth_type=row.auth_type,
        user_name=row.user_name,
        user_passwd=row.user_passwd,
        api_key=row.api_key,
        remark=row.remark,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_patch_dict(body: OcrToolPatchIn) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {}
    for key, value in data.items():
        if key in ("name", "url") and isinstance(value, str):
            patch[key] = value.strip()
        elif key == "auth_type":
            if value is None:
                patch[key] = None
            elif isinstance(value, str):
                patch[key] = _normalize_ocr_auth_type(value)
            else:
                patch[key] = value
        else:
            patch[key] = value
    return patch


@router.get("", response_model=list[OcrToolListItemOut])
async def list_ocr_tools(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[OcrToolListItemOut]:
    rows = await list_tools(session, workspace_id=workspace_id)
    return [_to_list_item(row) for row in rows]


@router.post("", response_model=OcrToolDetailOut, status_code=status.HTTP_201_CREATED)
async def create_ocr_tool(
    workspace_id: uuid.UUID,
    body: OcrToolCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrToolDetailOut:
    row = await create_tool(
        session,
        workspace_id=workspace_id,
        name=body.name,
        url=body.url,
        auth_type=_normalize_ocr_auth_type(body.auth_type),
        user_name=body.user_name,
        user_passwd=body.user_passwd,
        api_key=body.api_key,
        remark=body.remark,
    )
    return _to_detail(row)


@router.get("/{tool_id}", response_model=OcrToolDetailOut)
async def get_ocr_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrToolDetailOut:
    row = await get_tool(session, workspace_id=workspace_id, tool_id=tool_id)
    return _to_detail(row)


@router.patch("/{tool_id}", response_model=OcrToolDetailOut)
async def patch_ocr_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    body: OcrToolPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> OcrToolDetailOut:
    patch = _to_patch_dict(body)
    if not patch:
        row = await get_tool(session, workspace_id=workspace_id, tool_id=tool_id)
        return _to_detail(row)
    row = await update_tool(
        session,
        workspace_id=workspace_id,
        tool_id=tool_id,
        patch=patch,
    )
    return _to_detail(row)


@router.delete("/{tool_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
async def remove_ocr_tool(
    workspace_id: uuid.UUID,
    tool_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await delete_tool(session, workspace_id=workspace_id, tool_id=tool_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
