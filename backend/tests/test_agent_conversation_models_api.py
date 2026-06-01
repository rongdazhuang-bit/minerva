"""Tests for GET /agent/v2/models."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.agent.api.v2.router import router as agent_v2_router
from app.core.api.deps import require_workspace_member
from app.dependencies import get_db
from app.errors import register_exception_handlers

TEST_WORKSPACE_ID = uuid.UUID("00000000-0000-4000-8000-000000000001")


async def _allow_workspace(workspace_id: uuid.UUID) -> uuid.UUID:
    return workspace_id


@pytest.fixture
def agent_models_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    row = SimpleNamespace(
        id=uuid.uuid4(),
        provider_name="OpenAI",
        model_name="gpt-test",
        endpoint_url="https://example.com/v1",
        max_tokens_to_sample=4096,
        tags=["CHAT", "TEXT"],
    )
    monkeypatch.setattr(
        "app.agent.api.v2.router.model_repo.list_agent_conversation_models",
        AsyncMock(return_value=[row]),
    )
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(agent_v2_router)
    app.dependency_overrides[require_workspace_member] = _allow_workspace

    async def _fake_db():
        yield AsyncMock()

    app.dependency_overrides[get_db] = _fake_db
    return TestClient(app)


def test_list_agent_conversation_models_maps_max_tokens(
    agent_models_client: TestClient,
) -> None:
    res = agent_models_client.get(f"/workspaces/{TEST_WORKSPACE_ID}/agent/v2/models")
    assert res.status_code == 200
    body = res.json()
    assert len(body) == 1
    assert body[0]["provider_name"] == "OpenAI"
    assert body[0]["model_name"] == "gpt-test"
    assert body[0]["endpoint_url"] == "https://example.com/v1"
    assert body[0]["max_tokens"] == 4096
    assert body[0]["tags"] == ["CHAT", "TEXT"]
    assert "api_key" not in body[0]
    assert "max_tokens_to_sample" not in body[0]
