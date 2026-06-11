"""Unit tests for tenant_service slug validation."""

from unittest.mock import AsyncMock

import pytest

from app.exceptions import AppError
from app.sys.tenant.service import tenant_service as svc


def test_validate_slug_accepts_valid_slug() -> None:
    """Lowercase alphanumeric slug with hyphen is valid."""

    assert svc.validate_slug("acme-corp") == "acme-corp"


def test_validate_slug_rejects_invalid_chars() -> None:
    """Slug with spaces is invalid even after lowercasing."""

    with pytest.raises(AppError) as exc:
        svc.validate_slug("My Tenant")
    assert exc.value.code == "tenant.invalid_slug"


def test_validate_slug_trims_and_lowercases() -> None:
    """Slug is normalized before validation."""

    assert svc.validate_slug("  Acme-1  ") == "acme-1"


@pytest.mark.asyncio
async def test_create_tenant_creates_default_workspace(monkeypatch) -> None:
    """Creating a tenant also inserts one default sys_workspaces row."""

    session = AsyncMock()
    added: list[object] = []

    def capture_add(obj: object) -> None:
        added.append(obj)

    session.add = capture_add
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    async def fake_commit(_session: object, *, code: str) -> None:
        return None

    monkeypatch.setattr(
        "app.sys.tenant.service.tenant_service._commit_or_conflict",
        fake_commit,
    )

    tenant = await svc.create_tenant(
        session,
        {"name": "Acme", "slug": "acme", "status": True, "remark": None},
    )

    assert tenant.name == "Acme"
    assert len(added) == 2
    workspace = added[1]
    assert workspace.name == "默认工作空间"
    assert workspace.slug == "default"
    assert workspace.status is True
    assert workspace.tenant_id is tenant.id
    session.flush.assert_awaited_once()
