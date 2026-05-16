"""Tests for dynamic skill tools loading."""

from __future__ import annotations

import json
import uuid

import pytest

from app.agent.infrastructure.skill_tool_context import SkillToolContext
from app.agent.infrastructure.skill_tools import load_tools_for_skills
from app.config import settings


@pytest.mark.asyncio
async def test_load_system_datetime_tool() -> None:
    """system_datetime tools.py registers get_system_datetime."""

    reg = load_tools_for_skills(["system_datetime"])
    assert reg.has_tool("get_system_datetime")
    raw = await reg.invoke("get_system_datetime", "{}")
    data = json.loads(raw)
    assert "iso" in data
    assert "unix" in data


def test_unknown_skill_skipped() -> None:
    """Unknown skill id yields empty registry."""

    reg = load_tools_for_skills(["not_a_real_skill_xyz"])
    assert reg.get_openai_tools_payload() == []


@pytest.mark.asyncio
async def test_load_file_tools_with_context(
    tmp_path: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """file skill registers six tools when ctx is provided."""

    monkeypatch.setattr(settings, "agent_files_root", str(tmp_path / "af"))
    ctx = SkillToolContext(workspace_id=uuid.uuid4())
    reg = load_tools_for_skills(["file"], ctx=ctx)
    for name in (
        "list_dir",
        "read_file",
        "write_file",
        "delete_path",
        "mkdir",
        "move_path",
    ):
        assert reg.has_tool(name), name
    raw = await reg.invoke("write_file", '{"path": "t.txt", "content": "x"}')
    data = json.loads(raw)
    assert data.get("ok") is True
