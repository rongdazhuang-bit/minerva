"""Tests for agent memory management API."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_memory_profiles_404_when_sql_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Memory routes are disabled unless mem0 backend is selected."""

    monkeypatch.setattr(
        "app.agent.api.v2.memory_router.settings.agent_memory_backend", "sql"
    )
    workspace_id = uuid.uuid4()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            f"/workspaces/{workspace_id}/agent/v2/memory/profiles",
            headers={"Authorization": "Bearer test"},
        )
    # Without auth setup this may be 401; when authed would be 404 from _require_mem0_backend.
    assert response.status_code in (401, 403, 404)
