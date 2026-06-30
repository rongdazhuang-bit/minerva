"""Tests for local gateway and file service."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.exceptions import AppError
from app.local.infrastructure.local_gateway import LocalGateway
from app.local.service.local_file_service import LocalFileService
from app.sys.file_storage.service.storage_resolver import ActiveStorage


def test_local_gateway_roundtrip(tmp_path: Path) -> None:
    """Gateway can put, list, get, delete, and report existence for one object."""

    gw = LocalGateway(root=tmp_path)
    gw.put_object(object_key="ocr/2026/06/x.txt", payload=b"hi", content_type="text/plain")
    assert gw.get_object_bytes(object_key="ocr/2026/06/x.txt") == b"hi"
    items = gw.list_objects(prefix="ocr/")
    assert len(items) == 1
    gw.delete_object(object_key="ocr/2026/06/x.txt")
    assert not gw.exists(object_key="ocr/2026/06/x.txt")


@pytest.mark.asyncio
async def test_local_file_service_rejects_when_s3_active() -> None:
    """Service raises when workspace active storage is S3 instead of local."""

    session = AsyncMock()
    service = LocalFileService(session=session)
    workspace_id = uuid.uuid4()
    active = ActiveStorage(kind="S3", storage_id=uuid.uuid4(), local_path=None)

    with patch(
        "app.local.service.local_file_service.resolve_active_storage",
        new=AsyncMock(return_value=active),
    ):
        with pytest.raises(AppError) as exc:
            await service.upload_file(
                workspace_id=workspace_id,
                module_prefix="ocr",
                file_name="x.txt",
                payload=b"hi",
                content_type="text/plain",
            )

    assert exc.value.code == "local.storage_not_active"
    assert exc.value.status_code == 422
