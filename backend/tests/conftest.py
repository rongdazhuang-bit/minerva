"""Shared pytest fixtures for backend API tests."""

from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient

from app.agent.api.v2.skills_mgmt_router import router as skills_mgmt_router
from app.core.api.deps import require_tenant_owner_or_admin
from app.errors import register_exception_handlers
from app.exceptions import AppError

TEST_WORKSPACE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


@pytest.fixture
def skills_root_dir(tmp_path):
    """Minimal on-disk skills tree for skills-mgmt API tests."""

    root = tmp_path / "skills"
    root.mkdir()
    (root / "INDEX.md").write_text("# Index\n", encoding="utf-8")
    demo = root / "demo"
    demo.mkdir()
    (demo / "SKILL.md").write_text("# Demo\n", encoding="utf-8")
    return root


@pytest.fixture
def patch_skills_root(skills_root_dir, monkeypatch):
    """Route ``SkillFilesService`` default root to a temp directory."""

    monkeypatch.setattr(
        "app.agent.service.skill_files_service.skills_root",
        lambda: skills_root_dir,
    )
    return skills_root_dir


async def _deny_tenant_member(workspace_id: uuid.UUID) -> uuid.UUID:
    """Simulate tenant member denied by ``require_tenant_owner_or_admin``."""

    raise AppError("skills.forbidden", "Only tenant owner/admin can manage skills", 403)


async def _allow_tenant_admin(workspace_id: uuid.UUID) -> uuid.UUID:
    """Simulate tenant owner/admin passing the auth gate."""

    return workspace_id


def _make_skills_mgmt_app(auth_dep: Callable[..., object]) -> FastAPI:
    """Build a minimal FastAPI app exposing skills-mgmt routes."""

    app = FastAPI()
    register_exception_handlers(app)
    prefix_router = APIRouter(prefix="/workspaces/{workspace_id}/agent/v2")
    prefix_router.include_router(skills_mgmt_router)
    app.include_router(prefix_router)
    app.dependency_overrides[require_tenant_owner_or_admin] = auth_dep
    return app


@pytest.fixture
def member_client(patch_skills_root) -> Iterator[TestClient]:
    """HTTP client with tenant-member auth (skills-mgmt forbidden)."""

    app = _make_skills_mgmt_app(_deny_tenant_member)
    yield TestClient(app)


@pytest.fixture
def admin_client(patch_skills_root) -> Iterator[TestClient]:
    """HTTP client with tenant owner/admin auth for skills-mgmt."""

    app = _make_skills_mgmt_app(_allow_tenant_admin)
    yield TestClient(app)
