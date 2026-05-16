"""Tests for agent skill index and markdown loading."""

from __future__ import annotations

from app.agent.infrastructure import skill_loader


def test_parse_skill_ids_finds_system_datetime() -> None:
    """INDEX lists ``system_datetime``."""

    text = skill_loader.load_index_text()
    ids = skill_loader.parse_skill_ids_from_index(text)
    assert "system_datetime" in ids


def test_load_skill_markdown_system_datetime() -> None:
    """``system_datetime/SKILL.md`` loads non-empty."""

    body = skill_loader.load_skill_markdown("system_datetime")
    assert len(body.strip()) > 0


def test_parse_skill_descriptions_from_index() -> None:
    """INDEX bullets yield id to description map."""

    text = skill_loader.load_index_text()
    desc = skill_loader.parse_skill_descriptions_from_index(text)
    assert "system_datetime" in desc
    assert "时间" in desc["system_datetime"] or "UTC" in desc["system_datetime"]


def test_list_indexed_skills_includes_system_datetime() -> None:
    """list_indexed_skills returns entries with existing SKILL.md."""

    items = skill_loader.list_indexed_skills()
    ids = [x["id"] for x in items]
    assert "system_datetime" in ids


def test_parse_skill_ids_finds_file() -> None:
    """INDEX lists ``file``."""

    text = skill_loader.load_index_text()
    ids = skill_loader.parse_skill_ids_from_index(text)
    assert "file" in ids


def test_load_skill_markdown_file() -> None:
    """``file/SKILL.md`` loads non-empty."""

    body = skill_loader.load_skill_markdown("file")
    assert len(body.strip()) > 0
