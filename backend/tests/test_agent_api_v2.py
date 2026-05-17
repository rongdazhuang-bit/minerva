"""HTTP-level tests for agent v2 routes (auth gates)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_agent_v2_create_session_requires_auth() -> None:
    """未携带 JWT 时创建会话应返回 401。"""

    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(f"/workspaces/{ws}/agent/v2/sessions", json={})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_v2_create_run_requires_auth() -> None:
    """未携带 JWT 时创建 run 应返回 401。"""

    ws = uuid.uuid4()
    sid = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/workspaces/{ws}/agent/v2/sessions/{sid}/runs",
            json={
                "user_message": "hi",
                "model_id": str(uuid.uuid4()),
            },
        )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_v2_list_capabilities_requires_auth() -> None:
    """未携带 JWT 时列出能力应返回 401。"""

    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/workspaces/{ws}/agent/v2/capabilities")
    assert res.status_code == 401
