"""Tests for agent skill index and markdown loading."""

from __future__ import annotations

from app.agent.infrastructure import skill_loader


def test_parse_skill_ids_finds_example_echo() -> None:
    """Index bullets with backticks and trailing text still yield ids."""

    text = skill_loader.load_index_text()
    ids = skill_loader.parse_skill_ids_from_index(text)
    assert "example_echo" in ids


def test_load_skill_markdown_example_echo() -> None:
    """``example_echo/SKILL.md`` loads non-empty."""

    body = skill_loader.load_skill_markdown("example_echo")
    assert "example" in body.lower() or "示例" in body
