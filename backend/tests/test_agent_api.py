"""HTTP-level tests for agent routes (auth gates)."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_agent_create_session_requires_auth() -> None:
    """未携带 JWT 时创建会话应返回 401。"""

    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(f"/workspaces/{ws}/agent/sessions", json={})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_list_sessions_requires_auth() -> None:
    """未携带 JWT 时列出会话应返回 401。"""

    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/workspaces/{ws}/agent/sessions")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_delete_session_requires_auth() -> None:
    """未携带 JWT 时删除会话应返回 401。"""

    ws = uuid.uuid4()
    sid = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.delete(f"/workspaces/{ws}/agent/sessions/{sid}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_get_session_requires_auth() -> None:
    """未携带 JWT 时获取会话详情应返回 401。"""

    ws = uuid.uuid4()
    sid = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/workspaces/{ws}/agent/sessions/{sid}")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_list_skills_requires_auth() -> None:
    """未携带 JWT 时列出技能应返回 401。"""

    ws = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.get(f"/workspaces/{ws}/agent/skills")
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_agent_create_run_requires_auth() -> None:
    """未携带 JWT 时创建 run 应返回 401。"""

    ws = uuid.uuid4()
    sid = uuid.uuid4()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        res = await ac.post(
            f"/workspaces/{ws}/agent/sessions/{sid}/runs",
            json={
                "user_message": "hi",
                "base_url": "http://localhost:4000/v1",
                "api_key": "sk",
                "model": "m",
            },
        )
    assert res.status_code == 401
