from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.dict.service import dictionary_service as dict_service
from app.sys.model_provider.domain.db.models import SysModel
from app.sys.model_provider.infrastructure import repository as repo

_LEGACY_MODEL_AUTH_TO_CANON: dict[str, str] = {
    "none": "NONE",
    "basic": "BASIC",
    "api_key": "API_KEY",
}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _normalize_model_auth_type(value: str) -> str:
    s = value.strip()
    if not s:
        raise AppError("model_provider.auth_type_invalid", "auth_type is required", 422)
    return _LEGACY_MODEL_AUTH_TO_CANON.get(s.lower(), s)


def _assert_auth_fields(
    *,
    auth_type: str,
    api_key: str | None,
    auth_name: str | None,
    auth_passwd: str | None,
    strict: bool,
) -> None:
    tag = _normalize_model_auth_type(auth_type)
    if tag == "API_KEY":
        if strict and not (api_key or "").strip():
            raise AppError(
                "model_provider.api_key_required",
                "api_key is required for API_KEY auth",
                422,
            )
    elif tag == "BASIC":
        if strict and (not (auth_name or "").strip() or not (auth_passwd or "").strip()):
            raise AppError(
                "model_provider.basic_creds_required",
                "auth_name and auth_passwd are required for BASIC auth",
                422,
            )
    elif tag == "NONE":
        return
    else:
        # Unknown auth type tags are allowed as strings, but we cannot validate field bundles.
        return


async def _load_dict_name_set(
    session: AsyncSession, *, workspace_id: uuid.UUID, dict_code: str
) -> set[str]:
    items = await dict_service.list_items_by_dict_code(
        session, workspace_id=workspace_id, dict_code=dict_code
    )
    if not items:
        raise AppError(
            "model_provider.dict_not_configured",
            f"Dictionary {dict_code} is missing or has no items",
            422,
        )
    return {i.name.strip() for i in items if (i.name or "").strip()}


async def _validate_model_fields(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    provider_name: str,
    model_type: str,
    auth_type: str,
    api_key: str | None,
    auth_name: str | None,
    auth_passwd: str | None,
    strict_auth: bool,
) -> None:
    allowed_providers = await _load_dict_name_set(
        session, workspace_id=workspace_id, dict_code="MODEL_PROVIDER"
    )
    if provider_name.strip() not in allowed_providers:
        raise AppError("model_provider.provider_name_invalid", "Invalid provider_name", 422)

    allowed_types = await _load_dict_name_set(
        session, workspace_id=workspace_id, dict_code="MODEL_TYPE"
    )
    if model_type.strip() not in allowed_types:
        raise AppError("model_provider.model_type_invalid", "Invalid model_type", 422)

    _assert_auth_fields(
        auth_type=auth_type,
        api_key=api_key,
        auth_name=auth_name,
        auth_passwd=auth_passwd,
        strict=strict_auth,
    )


async def list_models(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> list[SysModel]:
    return list(await repo.list_for_workspace(session, workspace_id=workspace_id))


async def get_model(
    session: AsyncSession, *, workspace_id: uuid.UUID, model_id: uuid.UUID
) -> SysModel:
    row = await repo.get_for_workspace(
        session, workspace_id=workspace_id, model_id=model_id
    )
    if row is None:
        raise AppError("model_provider.not_found", "Model provider row not found", 404)
    return row


async def create_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    data: dict[str, Any],
) -> SysModel:
    await _validate_model_fields(
        session,
        workspace_id=workspace_id,
        provider_name=str(data["provider_name"]),
        model_type=str(data["model_type"]),
        auth_type=str(data["auth_type"]),
        api_key=data.get("api_key"),
        auth_name=data.get("auth_name"),
        auth_passwd=data.get("auth_passwd"),
        strict_auth=True,
    )
    now = _utc_now()
    row = SysModel(
        workspace_id=workspace_id,
        provider_name=str(data["provider_name"]).strip(),
        model_name=str(data["model_name"]).strip(),
        model_type=str(data["model_type"]).strip(),
        enabled=bool(data["enabled"]),
        load_balancing_enabled=bool(data["load_balancing_enabled"]),
        auth_type=_normalize_model_auth_type(str(data["auth_type"])),
        endpoint_url=data.get("endpoint_url"),
        api_key=data.get("api_key"),
        auth_name=data.get("auth_name"),
        auth_passwd=data.get("auth_passwd"),
        context_size=data.get("context_size"),
        max_tokens_to_sample=data.get("max_tokens_to_sample"),
        model_config=data.get("model_config"),
        create_at=now,
        update_at=now,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def update_model(
    session: AsyncSession,
    *,
    workspace_id: uuid.UUID,
    model_id: uuid.UUID,
    patch: dict[str, Any],
) -> SysModel:
    row = await get_model(session, workspace_id=workspace_id, model_id=model_id)
    for key, value in patch.items():
        if key == "auth_type" and isinstance(value, str):
            setattr(row, key, _normalize_model_auth_type(value))
        else:
            setattr(row, key, value)
    await _validate_model_fields(
        session,
        workspace_id=workspace_id,
        provider_name=row.provider_name,
        model_type=row.model_type,
        auth_type=row.auth_type,
        api_key=row.api_key,
        auth_name=row.auth_name,
        auth_passwd=row.auth_passwd,
        strict_auth=False,
    )
    row.update_at = _utc_now()
    await session.commit()
    await session.refresh(row)
    return row


async def delete_model(
    session: AsyncSession, *, workspace_id: uuid.UUID, model_id: uuid.UUID
) -> None:
    row = await get_model(session, workspace_id=workspace_id, model_id=model_id)
    await session.delete(row)
    await session.commit()


@dataclass
class GroupedModelProviders:
    provider_name: str
    items: list[SysModel]


def group_by_provider_name(rows: Iterable[SysModel]) -> list[GroupedModelProviders]:
    m: dict[str, list[SysModel]] = defaultdict(list)
    for r in rows:
        m[r.provider_name].append(r)
    for items in m.values():
        items.sort(
            key=lambda x: (x.create_at is None, x.create_at, x.id),
            reverse=True,
        )
    return [GroupedModelProviders(k, m[k]) for k in sorted(m.keys())]
