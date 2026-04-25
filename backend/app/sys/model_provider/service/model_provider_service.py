from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Iterable

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.model_provider.domain.db.models import SysModel
from app.sys.model_provider.infrastructure import repository as repo


def _utc_now() -> datetime:
    return datetime.now(UTC)


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
    now = _utc_now()
    row = SysModel(
        workspace_id=workspace_id,
        provider_name=data["provider_name"],
        model_name=data["model_name"],
        model_type=data["model_type"],
        enabled=bool(data["enabled"]),
        load_balancing_enabled=bool(data["load_balancing_enabled"]),
        auth_type=data["auth_type"],
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
        setattr(row, key, value)
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
