"""Tests for dynamic skill tools loading."""

from __future__ import annotations

import json

import pytest

from app.agent.infrastructure.skill_tools import load_tools_for_skills


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
