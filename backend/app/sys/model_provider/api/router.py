"""Workspace-level routes managing configured LLM providers and catalog models."""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api.deps import get_current_user, require_workspace_member, require_workspace_owner_or_admin
from app.dependencies import get_db
from app.core.domain.identity.models import User
from app.sys.model_provider.api.schemas import (
    ModelProviderCreateIn,
    ModelProviderDetailOut,
    ModelProviderGroupItemOut,
    ModelProviderGroupOut,
    ModelProviderListItemOut,
    ModelProviderPatchIn,
)
from app.sys.model_provider.domain.db.models import SysModel
from app.sys.model_provider.service import model_provider_service as svc


router = APIRouter(
    prefix="/workspaces/{workspace_id}/model-providers",
    tags=["model-providers"],
)


def _to_list_item(row: SysModel) -> ModelProviderListItemOut:
    return ModelProviderListItemOut(
        id=row.id,
        provider_name=row.provider_name,
        model_name=row.model_name,
        model_type=row.model_type,
        enabled=row.enabled,
        load_balancing_enabled=row.load_balancing_enabled,
        auth_type=row.auth_type,
        endpoint_url=row.endpoint_url,
        has_api_key=bool(row.api_key),
        has_password=bool(row.auth_passwd),
        context_size=row.context_size,
        max_tokens_to_sample=row.max_tokens_to_sample,
        other_config=row.model_config,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_group_item(row: SysModel) -> ModelProviderGroupItemOut:
    return ModelProviderGroupItemOut(
        id=row.id,
        model_name=row.model_name,
        model_type=row.model_type,
        enabled=row.enabled,
        load_balancing_enabled=row.load_balancing_enabled,
        auth_type=row.auth_type,
        endpoint_url=row.endpoint_url,
        has_api_key=bool(row.api_key),
        has_password=bool(row.auth_passwd),
        context_size=row.context_size,
        max_tokens_to_sample=row.max_tokens_to_sample,
        other_config=row.model_config,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_detail(row: SysModel) -> ModelProviderDetailOut:
    return ModelProviderDetailOut(
        id=row.id,
        workspace_id=row.workspace_id,
        provider_name=row.provider_name,
        model_name=row.model_name,
        model_type=row.model_type,
        enabled=row.enabled,
        load_balancing_enabled=row.load_balancing_enabled,
        auth_type=row.auth_type,
        endpoint_url=row.endpoint_url,
        api_key=row.api_key,
        auth_name=row.auth_name,
        auth_passwd=row.auth_passwd,
        context_size=row.context_size,
        max_tokens_to_sample=row.max_tokens_to_sample,
        other_config=row.model_config,
        create_at=row.create_at,
        update_at=row.update_at,
    )


def _to_create_dict(body: ModelProviderCreateIn) -> dict[str, Any]:
    return {
        "provider_name": body.provider_name.strip(),
        "model_name": body.model_name.strip(),
        "model_type": body.model_type.strip(),
        "enabled": body.enabled,
        "load_balancing_enabled": body.load_balancing_enabled,
        "auth_type": body.auth_type.strip(),
        "endpoint_url": body.endpoint_url.strip() if body.endpoint_url else None,
        "api_key": body.api_key,
        "auth_name": body.auth_name,
        "auth_passwd": body.auth_passwd,
        "context_size": body.context_size,
        "max_tokens_to_sample": body.max_tokens_to_sample,
        "model_config": body.other_config,
    }


def _to_patch_dict(body: ModelProviderPatchIn) -> dict[str, Any]:
    data = body.model_dump(exclude_unset=True)
    patch: dict[str, Any] = {}
    for key, value in data.items():
        if key == "other_config":
            patch["model_config"] = value
            continue
        if key in ("provider_name", "model_name", "model_type", "auth_type") and isinstance(
            value, str
        ):
            patch[key] = value.strip()
        elif key == "endpoint_url" and isinstance(value, str):
            patch[key] = value.strip() or None
        else:
            patch[key] = value
    return patch


@router.get("/models", response_model=list[ModelProviderListItemOut])
async def list_models(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[ModelProviderListItemOut]:
    rows = await svc.list_models(session, workspace_id=workspace_id)
    return [_to_list_item(r) for r in rows]


@router.get("/grouped", response_model=list[ModelProviderGroupOut])
async def list_model_providers_grouped(
    workspace_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> list[ModelProviderGroupOut]:
    rows = await svc.list_models(session, workspace_id=workspace_id)
    grouped = svc.group_by_provider_name(rows)
    return [
        ModelProviderGroupOut(
            provider_name=g.provider_name,
            items=[_to_group_item(r) for r in g.items],
        )
        for g in grouped
    ]


@router.post(
    "/models",
    response_model=ModelProviderDetailOut,
    status_code=status.HTTP_201_CREATED,
)
async def create_model(
    workspace_id: uuid.UUID,
    body: ModelProviderCreateIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> ModelProviderDetailOut:
    row = await svc.create_model(
        session, workspace_id=workspace_id, data=_to_create_dict(body)
    )
    return _to_detail(row)


@router.get("/models/{model_id}", response_model=ModelProviderDetailOut)
async def get_model(
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_member),
    session: AsyncSession = Depends(get_db),
) -> ModelProviderDetailOut:
    row = await svc.get_model(session, workspace_id=workspace_id, model_id=model_id)
    return _to_detail(row)


@router.patch("/models/{model_id}", response_model=ModelProviderDetailOut)
async def patch_model(
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    body: ModelProviderPatchIn,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> ModelProviderDetailOut:
    patch = _to_patch_dict(body)
    if not patch:
        row = await svc.get_model(
            session, workspace_id=workspace_id, model_id=model_id
        )
        return _to_detail(row)
    row = await svc.update_model(
        session, workspace_id=workspace_id, model_id=model_id, patch=patch
    )
    return _to_detail(row)


@router.delete(
    "/models/{model_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_model(
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    _user: User = Depends(get_current_user),
    _workspace: uuid.UUID = Depends(require_workspace_owner_or_admin),
    session: AsyncSession = Depends(get_db),
) -> Response:
    await svc.delete_model(session, workspace_id=workspace_id, model_id=model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
