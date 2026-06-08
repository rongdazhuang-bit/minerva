"""Smoke tests for dataset API routes."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dataset.api.router import router as dataset_router
from app.errors import register_exception_handlers

TEST_WORKSPACE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


async def _allow_member(workspace_id: uuid.UUID) -> uuid.UUID:
    """Bypass workspace membership check in tests."""

    return workspace_id


@pytest.fixture
def dataset_client(monkeypatch) -> Iterator[TestClient]:
    """HTTP client with dataset routes and auth override."""

    from app.core.api import deps

    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(dataset_router)
    app.dependency_overrides[deps.require_workspace_member] = _allow_member
    monkeypatch.setattr(
        "app.core.api.deps.get_current_user",
        lambda: type("User", (), {"id": uuid.uuid4()})(),
    )
    yield TestClient(app)


def test_get_default_process_rule(dataset_client: TestClient) -> None:
    """Default process rule endpoint returns JSON payload."""

    response = dataset_client.get(f"/workspaces/{TEST_WORKSPACE_ID}/datasets/process-rule")
    assert response.status_code == 200
    body = response.json()
    assert "process_rule" in body
    assert body["process_rule"]["mode"] == "custom"
