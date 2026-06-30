"""Unit tests for active storage resolution."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from app.sys.file_storage.domain.db.models import SysStorage
from app.sys.file_storage.service.storage_resolver import resolve_active_storage


@dataclass
class _FakeResult:
    """Minimal SQLAlchemy result stub for mocked ``session.execute``."""

    value: SysStorage | None

    def scalar_one_or_none(self) -> SysStorage | None:
        """Return the configured row or ``None``."""
        return self.value


@pytest.mark.asyncio
async def test_resolve_default_local_when_no_enabled_row() -> None:
    """Fall back to DEFAULT_LOCAL when no enabled storage row exists."""
    session = AsyncMock()
    session.execute.return_value = _FakeResult(None)
    active = await resolve_active_storage(session, workspace_id=uuid.uuid4())
    assert active.kind == "DEFAULT_LOCAL"
    assert active.storage_id is None
    assert active.local_path is None


@pytest.mark.asyncio
async def test_resolve_s3_when_enabled_s3_row() -> None:
    """Resolve to S3 when the enabled row has type S3."""
    storage_id = uuid.uuid4()
    row = SysStorage(
        id=storage_id,
        workspace_id=uuid.uuid4(),
        type="S3",
        enabled=True,
        auth_type="NONE",
    )
    session = AsyncMock()
    session.execute.return_value = _FakeResult(row)
    active = await resolve_active_storage(session, workspace_id=uuid.uuid4())
    assert active.kind == "S3"
    assert active.storage_id == storage_id
    assert active.local_path is None


@pytest.mark.asyncio
async def test_resolve_local_when_enabled_local_row() -> None:
    """Resolve to LOCAL with local_path when the enabled row is LOCAL."""
    storage_id = uuid.uuid4()
    row = SysStorage(
        id=storage_id,
        workspace_id=uuid.uuid4(),
        type="LOCAL",
        enabled=True,
        local_path="backup",
        auth_type="NONE",
    )
    session = AsyncMock()
    session.execute.return_value = _FakeResult(row)
    active = await resolve_active_storage(session, workspace_id=uuid.uuid4())
    assert active.kind == "LOCAL"
    assert active.storage_id == storage_id
    assert active.local_path == "backup"
