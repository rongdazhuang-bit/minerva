"""Resolve the active file storage kind for one workspace."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import AppError
from app.sys.file_storage.infrastructure import repository as repo

ActiveStorageKind = Literal["S3", "LOCAL", "DEFAULT_LOCAL"]


@dataclass(frozen=True)
class ActiveStorage:
    """Effective storage backend for object file APIs within one workspace."""

    kind: ActiveStorageKind
    storage_id: uuid.UUID | None
    local_path: str | None


async def resolve_active_storage(
    session: AsyncSession, *, workspace_id: uuid.UUID
) -> ActiveStorage:
    """Return S3, LOCAL, or DEFAULT_LOCAL when no enabled row exists."""
    row = await repo.get_enabled_for_workspace(session, workspace_id=workspace_id)
    if row is None:
        return ActiveStorage(kind="DEFAULT_LOCAL", storage_id=None, local_path=None)
    storage_type = (row.type or "").strip().upper()
    if storage_type == "S3":
        return ActiveStorage(kind="S3", storage_id=row.id, local_path=None)
    if storage_type == "LOCAL":
        return ActiveStorage(kind="LOCAL", storage_id=row.id, local_path=row.local_path)
    raise AppError("file_storage.type_invalid", "Enabled storage type is invalid", 422)
